import { App, Stack, CfnOutput, RemovalPolicy } from 'aws-cdk-lib';
import { Bucket, BlockPublicAccess, BucketEncryption } from 'aws-cdk-lib/aws-s3';
const app = new App();
const stack = new Stack(app, 'SoundWorksSandbox', { env: { region: process.env.CDK_DEFAULT_REGION || 'us-west-2' } });
const assets = new Bucket(stack, 'PassageAssets', {
  blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
  encryption: BucketEncryption.S3_MANAGED,
  enforceSSL: true,
  versioned: true,
  removalPolicy: RemovalPolicy.RETAIN,
});
new CfnOutput(stack, 'PassageAssetsBucket', { value: assets.bucketName });
