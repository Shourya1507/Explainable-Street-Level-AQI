# AQI Delhi — Project Decisions

This file records every non-obvious decision made during the build, as required by rules.md §6.

---

## Architecture decisions

| Decision | Choice | Reason |
|---|---|---|
| Region | ap-south-1 (Mumbai) | Closest to Delhi data sources; Bedrock, SageMaker, Translate, Polly all available |
| Bedrock model | anthropic.claude-3-haiku-20240307-v1:0 | Fast, cheap, available in APAC; fallback to template if unavailable |
| Inference fallback | Lambda loads model from S3 | Avoids SageMaker endpoint cold-start and quota delays |
| Map renderer | MapLibre GL JS + OpenStreetMap tiles | Free fallback while Location Service is being set up |
| IaC tool | SAM (CloudFormation) | Lower setup cost than CDK for this timeline |
| Weather source | Open-Meteo (no key, free, historical + forecast) | Confirmed free access, no registration needed for <10k req/day |
| SHAP method | shap library in Lambda | Simpler than Clarify for tree models; same result |

## Data decisions

| Decision | Choice | Reason |
|---|---|---|
| OpenAQ pull | Public S3 archive (no key needed) | Faster, no rate limits, historical |
| Data window | 6 months (configurable) | Covers seasonal variation; S3 archive goes back years |
| Leakage guard | Exclude target station from neighbor features | Hardcoded check in feature builder |

## Open questions

- [ ] FIRMS MAP_KEY — need to register at https://firms.modaps.eosdis.nasa.gov/api/map_key/
- [ ] OpenAQ API key — needed only for live recent data; archive does not need it
- [ ] Bedrock account verification — pending (up to 2h for new accounts)
- [ ] Location Service map name and API key — to be created in ap-south-1

## Config values

| Variable | Value |
|---|---|
| Account ID | 991166714312 |
| Region | ap-south-1 |
| S3 raw bucket | aqi-raw-991166714312 |
| S3 features bucket | aqi-features-991166714312 |
| S3 models bucket | aqi-models-991166714312 |
| S3 frontend bucket | aqi-frontend-991166714312 |
| S3 audio bucket | aqi-audio-991166714312 |
| DynamoDB cache table | aqi-cache |
| SAM stack name | aqi-backend |
| API Gateway stages | dev (build), demo (judging) |
