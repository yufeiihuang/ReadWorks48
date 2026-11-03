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
    '/generated/*': {
      origin: S3BucketOrigin.withOriginAccessControl(assets),
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
})) new CfnOutput(stack, name, { value });
