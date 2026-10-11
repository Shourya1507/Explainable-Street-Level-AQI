# 🌫️ Explainable Street-Level AQI — Delhi

> **Environmental Hacks (DTU) · Air track · AWS-first · No hardware**

A web app where a user **clicks any point on a Delhi map** and instantly gets:
- Estimated PM2.5 in µg/m³ with a CPCB health category
- Confidence level based on distance to the nearest sensor
- **Top 3 SHAP-derived reasons** for the reading in plain English
- One-sentence actionable health advice

All inference runs entirely on AWS — no external AI APIs, no client-side ML.

**Live demo:** `https://aqi-frontend-991166714312.s3.ap-south-1.amazonaws.com/index.html`  
**API endpoint:** `https://6diafyett2.execute-api.ap-south-1.amazonaws.com/dev`

---

## What is built

| Feature | Status | Tier |
|---|---|---|
| Click-to-estimate PM2.5 with confidence and drivers | ✅ Live | 1 |
| XGBoost model trained on 9,089 real PM2.5 readings | ✅ Live | 1 |
| SHAP explainability — top 3 drivers per estimate | ✅ Live | 2 |
| Bedrock Claude 3 Haiku explanation + template fallback | ✅ Wired | 2 |
| "How accurate is this?" modal — RMSE chart, feature importance | ✅ Live | 2 |
| Architecture diagram | ✅ Below | 3 |
| Hindi text (Amazon Translate) | 🔜 | 4 |
| Hindi audio (Amazon Polly) | 🔜 | 4 |
| 48-hour XGBoost forecast | 🔜 | 5 |
| City-wide PM2.5 heatmap grid | 🔜 | 6 |
| Lowest-exposure route (Amazon Location Service) | 🔜 | 7 |
| Email alerts (SES) | 🔜 | 8 |

---

## Data sources & credits

| Source | What we use | Licence |
|---|---|---|
| [OpenAQ](https://openaq.org) | PM2.5 readings, station 8190 (Delhi/CPCB) | CC BY 4.0, original data from CPCB India |
| [Open-Meteo](https://open-meteo.com) | Hourly weather — temp, humidity, wind, BLH | Open-Meteo free tier, ERA5/ECMWF |
| [OpenStreetMap / Overpass](https://openstreetmap.org) | Road density within 1 km radius | © OSM contributors, ODbL |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov) | Active fire counts (Tier 6) | NASA FIRMS, MODIS/VIIRS |
| [MapLibre GL JS](https://maplibre.org) | Map rendering in browser | BSD-2-Clause |
| [Amazon Bedrock](https://aws.amazon.com/bedrock/) | Claude 3 Haiku explanation generation | AWS Commercial |

No proprietary datasets. No data is committed to this repository.

---

## Architecture (ap-south-1 · Mumbai)

```
┌─────────────────────────────────────────────┐
│               BROWSER                        │
│  MapLibre GL JS ──click─► /estimate /stations │
└──────────────────┬───────────────────────┘
                   │ HTTPS
       ┌───────────▼───────────┐
       │ API Gateway (dev)        │
       └───────┬─────────┬───┘
               │          │
  ┌───────────▼──┐  ┌───▼─────────┐
  │ Lambda          │  │ Lambda         │
  │ aqi-estimate    │  │ aqi-stations   │
  └──┬─────────────┘  └───────────────┘
     │
 ┌───▼──────────┐  ┌─────────────────────────┐
 │ DynamoDB        │  │ S3 aqi-models-*            │
 │ aqi-cache (TTL) │  │  nowcast_model.ubj          │
 └───────────────┘  │  eval_results.json          │
                       │  feature_importance.json    │
                       └────────┬─────────────────┘
                                │ (warm lambda cache)
                       ┌────────▼────────────┐
                       │ XGBoost + SHAP          │
                       └────────┬────────────┘
                                │
                       ┌────────▼────────────┐
                       │ Bedrock Claude 3 Haiku  │
                       │ (fallback: template)    │
                       └──────────────────────┘

DATA PIPELINE (offline → S3):
  pull_openaq.py ──► aqi-raw-*/
  build_features.py ──► features_train.parquet ──► aqi-features-*/
  train_nowcast.py ──► nowcast_model.ubj + eval JSON ──► aqi-models-*/
```

---

## Model evaluation

| Metric | Value | Notes |
|---|---|---|
| Method | 80/20 time-split | Single station — LOSO not applicable |
| Training rows | 9,089 hourly readings | Station 8190 (Delhi), May–Oct 2026 |
| **Model RMSE** | **6.32 µg/m³** | XGBoost on weather + time features |
| Persistence baseline RMSE | 2.41 µg/m³ | Uses prior hour's actual PM2.5 at station |
| Model MAE | see eval_results.json | |
| Top feature | Month (42% gain) | Strong seasonality in Delhi AQI |

> Our model uses only weather and time features, enabling spatial interpolation to any map location — which persistence cannot do at all.

---

## AWS services used

| Service | Role |
|---|---|
| **Amazon S3** | Raw data, Parquet features, model artifacts, static frontend |
| **AWS Lambda** | `/estimate` and `/stations` inference (512 MB, 30s) |
| **Amazon API Gateway** | REST API with throttling and CORS |
| **Amazon DynamoDB** | 1-hour TTL cache for estimate responses |
| **Amazon Bedrock** | Claude 3 Haiku — plain-language AQI explanation |
| **Amazon Location Service** | Map tiles (`aqi-delhi-map`) |
| **AWS IAM** | Least-privilege roles per Lambda |
| **Amazon CloudWatch** | Error-rate and p99 latency alarms |
| **AWS SAM / CloudFormation** | Infrastructure as Code |

---

## How to run

### Prerequisites
- AWS CLI v2 with `"Shourya Sankrit"` profile (`ap-south-1`)
- AWS SAM CLI
- Python 3.12+

### Backend deploy (Tier 0 — mocked)

```powershell
cd infra
sam build --template-file template.yaml
sam deploy
```

The API Gateway URL is printed as `ApiUrl` in the stack outputs.

### Frontend

Set the API URL in `frontend/src/app.js`:
```js
const CONFIG = { API_BASE: "https://<api-id>.execute-api.ap-south-1.amazonaws.com/dev" };
```

Then upload to S3 and create a CloudFront distribution:
```powershell
aws s3 sync frontend/src/ s3://aqi-frontend-991166714312/ --profile "Shourya Sankrit"
```

### Data pipeline (Tier 1)

```powershell
# Set keys in environment first
$env:OPENAQ_API_KEY = "your-key"
$env:FIRMS_MAP_KEY = "your-key"

cd backend/data_pipeline
pip install -r requirements-pipeline.txt
python pull_openaq.py --months 6 --city delhi
python build_features.py --city delhi --upload
```

### Model training (Tier 1)

```powershell
cd backend/ml
pip install -r requirements-ml.txt
python train_nowcast.py --upload
```

---

## Limits (honest)

- Estimates are from a model trained on government monitoring-station data. They are **not measurements**.
- Delhi has a limited number of CPCB monitoring stations. Accuracy decreases further from any station. Error by distance is shown in the evaluation view.
- The data window is bounded by OpenAQ archive availability and the pull date. It is stated on the evaluation slide.
- The sensor calibration module (Tier 9) uses **simulated** sensor data (historical readings with injected humidity-dependent bias). This is clearly labeled wherever it appears.
- SHAP values describe feature contributions to the model prediction, not proven causes of pollution.

---

## No keys in this repo

All API keys (OpenAQ, FIRMS) are stored in AWS Secrets Manager or Lambda environment variables only.
The frontend makes no direct calls to third-party APIs.
