import { App, Stack, CfnOutput, Duration, RemovalPolicy } from 'aws-cdk-lib';
import { Bucket, BlockPublicAccess, BucketEncryption, EventType } from 'aws-cdk-lib/aws-s3';
import { Distribution, ViewerProtocolPolicy, CachePolicy, OriginRequestPolicy, AllowedMethods } from 'aws-cdk-lib/aws-cloudfront';
import { S3BucketOrigin, HttpOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import { NodejsFunction } from 'aws-cdk-lib/aws-lambda-nodejs';
import { Function as LambdaFunction, Runtime, Code } from 'aws-cdk-lib/aws-lambda';
import { HttpApi, HttpMethod } from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { LambdaDestination } from 'aws-cdk-lib/aws-s3-notifications';
import { StateMachine, DefinitionBody, Choice, Condition, Wait, WaitTime, Succeed, Fail } from 'aws-cdk-lib/aws-stepfunctions';
import { LambdaInvoke } from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { PolicyStatement } from 'aws-cdk-lib/aws-iam';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const app = new App();
const stack = new Stack(app, 'SoundWorksSandbox', {
  env: { region: process.env.CDK_DEFAULT_REGION || 'us-west-2' },
  description: 'SoundWorks hackathon reader, read-only API, and generation foundation',
});
const bucketDefaults = {
  blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
  encryption: BucketEncryption.S3_MANAGED,
  enforceSSL: true,
  versioned: true,
  removalPolicy: RemovalPolicy.RETAIN,
};
const assets = new Bucket(stack, 'PassageAssets', bucketDefaults);
const website = new Bucket(stack, 'ReaderWebsite', bucketDefaults);
const apiFunction = new NodejsFunction(stack, 'PassageApi', {
  entry: resolve(root, 'apps/api/handler.js'),
  handler: 'handler',
  runtime: Runtime.NODEJS_24_X,
  depsLockFilePath: resolve(root, 'package-lock.json'),
  projectRoot: root,
  memorySize: 256,
  timeout: Duration.seconds(15),
  bundling: { minify: true, sourceMap: true, target: 'node24' },
});
const api = new HttpApi(stack, 'ReaderApi', { createDefaultStage: true });
const integration = new HttpLambdaIntegration('ExpressIntegration', apiFunction);
api.addRoutes({ path: '/api/{proxy+}', methods: [HttpMethod.GET], integration });
const generator = new LambdaFunction(stack, 'AudioGeneration', {
  runtime: Runtime.PYTHON_3_14,
  handler: 'handler.handler',
  code: Code.fromAsset(resolve(root, 'generation'), { exclude: ['.venv', '__pycache__', 'output'] }),
  memorySize: 256,
  timeout: Duration.seconds(300),
  environment: { ASSET_BUCKET: assets.bucketName, POLLY_ENGINE: 'neural', POLLY_VOICE: 'Stephen' },
});
// Generation is IAM-invoked only, never exposed by the public reader API.
assets.grantReadWrite(generator, 'generated/*');
assets.grantRead(generator, 'passages/*');
assets.addEventNotification(EventType.OBJECT_CREATED, new LambdaDestination(generator),
  { prefix: 'passages/', suffix: '.json' });
generator.addToRolePolicy(new PolicyStatement({ actions: ['polly:SynthesizeSpeech'], resources: ['*'] }));
// Human recordings are prepared asynchronously: Lambda starts/checks work, while
// Step Functions waits between polls. No warm worker or long-running Lambda is needed.
const humanTask = new LambdaFunction(stack, 'HumanAudioPreparation', {
  runtime: Runtime.PYTHON_3_14,
  handler: 'human_handler.handler',
  code: Code.fromAsset(resolve(root, 'generation'), { exclude: ['.venv', '__pycache__', 'output'] }),
  memorySize: 512,
  timeout: Duration.seconds(120),
  environment: { ASSET_BUCKET: assets.bucketName },
});
assets.grantRead(humanTask, 'human-passages/*');
assets.grantRead(humanTask, 'human-input/*');
assets.grantRead(humanTask, 'human-transcripts/*');
assets.grantPut(humanTask, 'human-transcripts/*');
assets.grantRead(humanTask, 'generated/*');
assets.grantPut(humanTask, 'generated/*');
humanTask.addToRolePolicy(new PolicyStatement({
  actions: ['transcribe:GetTranscriptionJob'],
  resources: [stack.formatArn({ service: 'transcribe', resource: 'transcription-job', resourceName: 'soundworks-human-*' })],
}));
// StartTranscriptionJob does not support job-ARN resource scoping. Constrain
// its required wildcard grant to our private output bucket and transcript prefix.
humanTask.addToRolePolicy(new PolicyStatement({
  actions: ['transcribe:StartTranscriptionJob'], resources: ['*'],
  conditions: {
    StringEquals: { 'transcribe:OutputBucketName': assets.bucketName },
    StringLike: { 'transcribe:OutputKey': 'human-transcripts/*' },
  },
}));
const advanceHuman = new LambdaInvoke(stack, 'AdvanceHumanAudio', {
  lambdaFunction: humanTask, outputPath: '$.Payload',
});
advanceHuman.addRetry({ errors: ['ClientError', 'EndpointConnectionError', 'ReadTimeoutError'],
  interval: Duration.seconds(10), maxAttempts: 3, backoffRate: 2 });
const humanReady = new Succeed(stack, 'HumanAudioReady');
const humanSuperseded = new Succeed(stack, 'HumanSourceUpdated');
const humanFailed = new Fail(stack, 'HumanTranscriptionFailed', { cause: 'Transcribe job failed; inspect workflow output for FailureReason' });
const waitForHuman = new Wait(stack, 'WaitForHumanTranscript', { time: WaitTime.duration(Duration.seconds(30)) });
const humanResult = new Choice(stack, 'HumanAudioStatus')
  .when(Condition.stringEquals('$.status', 'ready'), humanReady)
  .when(Condition.stringEquals('$.status', 'superseded'), humanSuperseded)
  .when(Condition.stringEquals('$.status', 'failed'), humanFailed)
  .otherwise(waitForHuman.next(advanceHuman));
const humanWorkflow = new StateMachine(stack, 'HumanAudioWorkflow', {
  definitionBody: DefinitionBody.fromChainable(advanceHuman.next(humanResult)),
  timeout: Duration.minutes(30),
});
const humanStarter = new LambdaFunction(stack, 'StartHumanAudio', {
  runtime: Runtime.PYTHON_3_14, handler: 'human_start.handler',
  code: Code.fromAsset(resolve(root, 'generation'), { exclude: ['.venv', '__pycache__', 'output'] }),
  memorySize: 128, timeout: Duration.seconds(30),
  environment: { ASSET_BUCKET: assets.bucketName, HUMAN_WORKFLOW_ARN: humanWorkflow.stateMachineArn },
});
humanWorkflow.grantStartExecution(humanStarter);
assets.addEventNotification(EventType.OBJECT_CREATED, new LambdaDestination(humanStarter),
  { prefix: 'human-passages/', suffix: '.json' });
const generatedOrigin = S3BucketOrigin.withOriginAccessControl(assets);
const distribution = new Distribution(stack, 'ReaderDistribution', {
  defaultRootObject: 'index.html',
  defaultBehavior: {
    origin: S3BucketOrigin.withOriginAccessControl(website),
    viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
    cachePolicy: CachePolicy.CACHING_OPTIMIZED,
    compress: true,
  },
  additionalBehaviors: {
    '/api/*': {
      origin: new HttpOrigin(`${api.apiId}.execute-api.${stack.region}.${stack.urlSuffix}`),
      viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      allowedMethods: AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
      cachePolicy: CachePolicy.CACHING_DISABLED,
      originRequestPolicy: OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
    },
    '/generated/*/current.json': {
      origin: generatedOrigin,
      viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: CachePolicy.CACHING_DISABLED,
      compress: true,
    },
    '/generated/*': {
      origin: generatedOrigin,
      viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: CachePolicy.CACHING_OPTIMIZED,
      compress: true,
    },
  },
});
new BucketDeployment(stack, 'PublishReader', {
  sources: [Source.asset(resolve(root, 'apps/reader/dist'))],
  destinationBucket: website,
  distribution,
  distributionPaths: ['/*'],
});
for (const [name, value] of Object.entries({
  ReaderUrl: `https://${distribution.distributionDomainName}`,
  ApiUrl: api.apiEndpoint,
  PassageAssetsBucket: assets.bucketName,
  WebsiteBucket: website.bucketName,
  GenerationFunctionName: generator.functionName,
  HumanAudioStarterName: humanStarter.functionName,
  HumanAudioWorkflowArn: humanWorkflow.stateMachineArn,
})) new CfnOutput(stack, name, { value });
