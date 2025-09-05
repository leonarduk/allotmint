# Observability

## Logs

- Backend uses Python's `logging` module. Configuration lives in `logging.ini`.
- When deployed on AWS Lambda, logs are available in CloudWatch log groups named `/aws/lambda/<FunctionName>`.
- Local runs print logs to the console.

## Dashboards

- No dashboards are provisioned by default.
- Create CloudWatch dashboards to track metrics such as `Invocations`, `Errors`, and `Duration` for `BackendLambda` and the scheduled `PriceRefreshLambda`.

## Alarms

Alerts can be forwarded through multiple transports:

- Set `SNS_TOPIC_ARN` to publish alerts to an AWS SNS topic.
- Provide `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to forward alerts to Telegram.

CloudWatch alarms can target the SNS topic, for example:

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name BackendErrors \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --dimensions Name=FunctionName,Value=BackendLambda \
  --evaluation-periods 1 \
  --alarm-actions $SNS_TOPIC_ARN
```
