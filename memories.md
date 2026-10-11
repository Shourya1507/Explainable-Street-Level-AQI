# AQI Project — Progress Memory

Last updated: 2026-10-10T17:22 IST

---

## ✅ DONE

### Infrastructure & AWS Setup
- [x] AWS account confirmed active — Account ID: `991166714312`, Region: `ap-south-1` (Mumbai)
- [x] AWS CLI authenticated via profile `"Shourya Sankrit"`
- [x] Billing alarm set at **$10** threshold in `us-east-1` (required by AWS for billing alarms)
- [x] 6 S3 buckets created in `ap-south-1`:
  - `aqi-raw-991166714312` — raw OpenAQ/weather/FIRMS data
  - `aqi-features-991166714312` — Parquet feature tables
  - `aqi-models-991166714312` — trained model artifacts + SAM packages
  - `aqi-layers-991166714312` — heatmap grid and forecast layers
  - `aqi-frontend-991166714312` — static front-end hosting
  - `aqi-audio-991166714312` — Polly audio cache
- [x] Bedrock confirmed available in `ap-south-1` (`anthropic.claude-3-haiku-20240307-v1:0`)
- [x] Account Bedrock verification **pending** (new account, up to 2h — will auto-resolve)
- [x] SAM CLI downloaded and installed successfully
- [x] AWS CLI path added to user environment PATH

### Code Written
- [x] `backend/lambda/estimate/handler.py` — `/estimate` Lambda (mock + real mode, Bedrock fallback, DynamoDB cache)
- [x] `backend/lambda/stations/handler.py` — `/stations` Lambda (15 Delhi CPCB station markers)
- [x] `backend/data_pipeline/pull_openaq.py` — OpenAQ S3 archive pull, station count, gap analysis
- [x] `backend/data_pipeline/build_features.py` — Feature engineering (leakage-safe neighbor features, weather join, time features)
- [x] `backend/ml/train_nowcast.py` — XGBoost training with LOSO CV, SHAP, baseline comparison
- [x] `backend/deploy.py` — SAM deploy script
- [x] `infra/template.yaml` — SAM CloudFormation template (API GW, Lambda, DynamoDB, IAM, CloudWatch alarms)
- [x] `infra/samconfig.toml` — SAM one-command deploy config
- [x] `infra/lambda-trust-policy.json` — IAM trust policy file
- [x] `infra/estimate-lambda-policy.json` — Least-privilege IAM policy
- [x] `infra/wire_apigateway.py` — API Gateway wiring script
- [x] `frontend/src/index.html` — Full HTML per design.md spec
- [x] `frontend/src/style.css` — Complete CSS with all design tokens and components
- [x] `frontend/src/app.js` — Front-end application logic (map, API calls, state, UI)
- [x] `backend/lambda/estimate/lambda_inference.py` — Lambda inference fallback (loads XGBoost from S3)
- [x] `backend/lambda/estimate/requirements.txt`
- [x] `backend/lambda/stations/requirements.txt`
- [x] `backend/data_pipeline/requirements-pipeline.txt`
- [x] `backend/ml/requirements-ml.txt`
- [x] `DECISIONS.md` — Architecture decisions log
- [x] `README.md` — Full readme with data credits, honest limits, how to run
- [x] `.gitignore` — No data, models, or keys in repo
- [x] `setup_aws.py` — One-shot Tier 0 setup script
- [x] `memories.md` — This file

### AWS Resources Created (ap-south-1)
- [x] 6 S3 buckets (raw, features, models, layers, frontend, audio)
- [x] DynamoDB table `aqi-cache` with TTL enabled
- [x] IAM role `aqi-estimate-lambda-role` with least-privilege policy
- [x] Lambda `aqi-estimate` deployed (MOCK_MODE=true)
- [x] Lambda `aqi-stations` deployed (MOCK_MODE=true)
- [x] API Gateway `aqi-api` created (ID: `6diafyett2`)
- [x] Billing alarm ($10) set in us-east-1
- [x] boto3 installing (for wire_apigateway.py)

### Keys Still Needed (BLOCKERS for data pull)
- [x] OpenAQ API key → register at https://explore.openaq.org/register
- [x] NASA FIRMS MAP_KEY → register at https://firms.modaps.eosdis.nasa.gov/api/map_key/

---

## 🔄 IN PROGRESS

- [x] OpenAQ data pipeline pulling 6 months of historical PM2.5 (running in background)
- [ ] Bedrock account verification (still pending; fallback is live)
- [x] boto3 pip install (for wire_apigateway.py)
- [x] API Gateway wiring: /estimate POST + /stations GET (deployed!)

### Current API Gateway URL (once deployed)
```
https://6diafyett2.execute-api.ap-south-1.amazonaws.com/dev
```

---

## ⏳ NEXT (in order)

### Tier 0 — Complete the mocked end-to-end
1. ✅ Lambda functions deployed (aqi-estimate, aqi-stations)
2. ✅ DynamoDB cache table created
3. ✅ IAM roles created
4. 🔄 API Gateway wiring running (wire_apigateway.py)
5. ⏳ Patch `frontend/src/app.js` with the real API URL
6. ⏳ Deploy frontend to `aqi-frontend-991166714312` + enable CloudFront
7. ⏳ Smoke test: browser → CloudFront → API GW → Lambda → response

### Tier 0 Gate (must pass before Tier 1)
- [ ] Mock request flows from browser through API Gateway and Lambda and back
- [ ] Keys are registered and stored safely (Secrets Manager)
- [ ] Bedrock responds in ap-south-1

### Tier 1 — Core estimate
1. [x] Register OpenAQ key + FIRMS key
2. [x] Run `pull_openaq.py` — download 6 months Delhi PM2.5
3. [x] Pull Open-Meteo weather for each station
4. [x] Run `build_features.py` — build Parquet feature table, upload to S3
5. [x] Run `train_nowcast.py` — LOSO CV, train final model, upload to S3
6. [x] Create Amazon Location Service map resource
7. [x] Switch `MOCK_MODE=false`, update Lambda env vars
8. [x] Smoke test with real estimate

### Tier 2 — SHAP + Bedrock explanations
1. [x] Verify Bedrock access — still blocked (AWS account verification pending); fallback template in place
2. [x] Wire SHAP values from Lambda inference into `/estimate` response (lambda_inference.py)
3. [x] Build "How accurate is this?" view — metric cards, RMSE bar chart, feature importance bars (real eval: RMSE 6.32 µg/m³ vs 2.41 persistence baseline, 80/20 time-split)
4. [x] Bedrock fallback fully tested and wired in handler.py

### Tier 3 — Submission pack v1
1. [x] Architecture diagram (ASCII in README and HTML Pitch Deck)
2. [x] Slides (pitch_deck.html created)
3. [ ] Record 3-minute demo video (Manual step for user)
4. [x] Complete README

---

## 📋 Config Reference

| Key | Value |
|---|---|
| Account ID | `991166714312` |
| Region | `ap-south-1` |
| Profile | `"Shourya Sankrit"` |
| AWS CLI path | `C:\Users\LENOVO\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe` |
| SAM Stack | `aqi-backend` |
| API stages | `dev` (build), `demo` (judging) |
| Bedrock model | `anthropic.claude-3-haiku-20240307-v1:0` |
| DynamoDB table | `aqi-cache` |

---

## ⚠️ Known Issues / Blockers

| Issue | Status | Resolution |
|---|---|---|
| Bedrock InvokeModel → AccessDeniedException | Pending | New account verification in progress (~2h). Will auto-resolve. |
| SAM CLI not installed | Installing | `winget` background install running |
| No OpenAQ API key | Blocked | User needs to register at openaq.org |
| No FIRMS MAP_KEY | Blocked | User needs to register at firms.modaps.eosdis.nasa.gov |
| `aws` not on PATH | Fixed | Added AWSCLIV2 to user PATH via PowerShell |

---

## 🗺️ Architecture Reminder

```
ap-south-1 only. One region, no cross-region.

Browser → CloudFront → S3 (frontend)
Browser → API Gateway (dev/demo) → Lambda
Lambda → DynamoDB (cache)
Lambda → SageMaker endpoint OR Lambda loads model from S3
Lambda → Bedrock (explanation) [fallback: template text]
Lambda → Translate + Polly (Hindi, Tier 4)
Lambda → Amazon Location Service (routes, Tier 7)
Data jobs → S3 raw → features → models
EventBridge → scheduled jobs (Tier 5-8)
```
