# PRD: Explainable Street-Level AQI

*Environmental Hacks (DTU) · Air track · Team of 2 · \~31-hour build · AWS-first · No hardware*

## 1. Overview

A web app where a user clicks any point on a map of Delhi and gets an estimated PM2.5 for that exact spot and time, a confidence level, the top three reasons for the reading in plain language, and one line of advice. The estimate comes from a model trained on existing government monitoring-station data plus weather and geography, so it works at places that have no sensor.

**One-line pitch:** Delhi has few monitoring stations, so most people have no idea what the air is like on their own street, or why. We estimate it block by block and explain every number.

**Full scope:** beyond the core estimate, the product also provides a 48-hour forecast, a heatmap layer, a low-cost sensor calibration module (fed by a simulated stream, no physical hardware), lowest-exposure route suggestions, multi-city support, Hindi text and audio, saved places with email alerts, and an authority dashboard. Nothing is cut for time; the timeline sequences the work by dependency.

## 2. Problem

- Monitoring stations are sparse. A single station reading is applied to a whole area, even though PM2.5 can differ a lot over short distances.
- Raw AQI numbers do not tell people *why* the air is bad or what to do about it.
- Existing apps show a number without uncertainty and without drivers, so users and authorities cannot judge how far to trust it.

## 3. Goals and non-goals

### Goals

1. Estimate PM2.5 at any covered coordinate and timestamp, including places with no station.
2. Show honest uncertainty (confidence level and distance to the nearest station).
3. Explain each estimate: top three drivers from SHAP, rewritten in plain language by Bedrock.
4. Show measured evidence that the model beats a nearest-station baseline on stations it never saw during training.
5. Make AWS services do real work at every layer (data, training, explanation, serving, maps, messaging, hosting).
6. Forecast PM2.5 up to 48 hours ahead and report accuracy by horizon against a persistence baseline.
7. Calibrate low-cost sensor readings against reference stations and report error before and after.
8. Suggest the lowest-exposure route between two points, with the time trade-off.
9. Serve multiple Indian cities from one config-driven system.
10. Deliver explanations in Hindi (text and audio) and send threshold alerts to signed-in users.

### Out of scope

- Physical sensors or any hardware. Everything runs on software and public data. The sensor stream in the calibration module is simulated unless real public low-cost data is found, and it is labeled as such wherever it appears.
- SMS alerts to Indian numbers, because they need telecom DLT registration. Email and in-app alerts are used instead.

## 4. Users

| User | Need | How the product serves them |
| --- | --- | --- |
| Resident or parent | "Is the air bad on my street right now, and what should I do?" | Click-to-estimate with advice line |
| Ward or pollution-control officer | "Where and why is it bad, and how reliable is this?" | Drivers and confidence on every estimate |
| Hackathon judge | "Is this technically sound and AWS-heavy?" | Held-out validation, SHAP, architecture diagram |

Primary persona for the demo: a resident checking a specific neighborhood.

## 5. User stories

1. As a resident, I click my neighborhood on the map and see an estimated PM2.5 and category (Good to Severe).
2. As a resident, I see the top three reasons the number is what it is, in a sentence I can understand.
3. As a resident, I see a one-line suggestion appropriate to the category.
4. As an officer, I see how far the nearest real station is and a confidence level, so I know when to trust the estimate.
5. As an officer, I can pick a different hour and see how the estimate and drivers change.
6. As a judge, I can see the evaluation results comparing the model with the baselines.
7. As a resident, I see the forecast for the next 48 hours at my location, so I can plan outdoor activity.
8. As a commuter, I enter a start and end point and get the route with the lowest expected exposure and the time it costs.
9. As a resident, I switch to Hindi and have the explanation read aloud.
10. As a signed-in user, I save places and get an email when forecast PM2.5 crosses my threshold.
11. As an officer, I see a dashboard of estimates by area, low-confidence areas, and sensor calibration results.
12. As a user in another city, I pick my city and get the same experience.

## 6. Functional requirements

| ID | Requirement | Build phase |
| --- | --- | --- |
| FR1 | Interactive map (Amazon Location Service). Click selects a point. City selector. | 1 |
| FR2 | Time selector: pick any hour within the available data window. Default is the latest hour. | 1 |
| FR3 | Backend returns estimated PM2.5, AQI category, confidence, nearest-station distance. | 1 |
| FR4 | Backend returns top three SHAP drivers with direction and magnitude. | 1 |
| FR5 | Bedrock converts drivers into one plain-language explanation and one advice line. | 1 |
| FR6 | Evaluation view: model vs baselines (leave-one-station-out), forecast error by horizon, calibration before and after. | 1-3 |
| FR7 | Station markers on the map, so viewers see where real data exists. | 1 |
| FR8 | Hindi text (Translate) and spoken explanation (Polly). | 1 |
| FR9 | Heatmap overlay from a precomputed grid, low-confidence cells shown differently. | 2 |
| FR10 | Rule-based fallback explanation if Bedrock fails or times out. | 1 |
| FR11 | 48-hour forecast with horizon chart and intervals. | 2 |
| FR12 | Route comparison: candidate routes ranked by exposure, with time and distance. | 2 |
| FR13 | Fire-detection and satellite aerosol features in the model and in the explanations. | 2 |
| FR14 | Low-cost sensor calibration module with a simulated sensor stream. | 3 |
| FR15 | Sign-in, saved places, and alert thresholds. | 3 |
| FR16 | Threshold alerts by email and in-app. | 3 |
| FR17 | Multi-city registry: data, stations, and model settings per city. | 3 |
| FR18 | Authority dashboard (QuickSight). | 3 |

Build phase is a build order, not a priority. All requirements are in scope.

## 7. UX flow

1. User lands on a Delhi map with station markers and the latest hour selected.
2. User clicks a point. A side panel shows a loading state, then:
   - Large PM2.5 value and category color.
   - Confidence badge (high, medium, low) with a one-line reason (for example, "nearest station 6.2 km away").
   - "Why": the plain-language explanation plus a small bar chart of the top three drivers.
   - "What to do": the advice line.
3. User changes the hour; the panel updates.
4. A separate "How accurate is this?" view shows the evaluation chart.

Design constraint: one screen, no navigation maze. The demo must work in under 60 seconds.

## 8. Data

| Data | Source | Use | Notes |
| --- | --- | --- | --- |
| PM2.5 station readings (Delhi and other target cities) | OpenAQ (historical and recent) | Training target and neighbor features | Check coverage and gaps in the first hours. Do not assume a station count in advance. |
| Weather, observed and forecast (temperature, humidity, wind speed and direction, pressure, boundary-layer height if available) | A free historical and forecast weather API, plus ERA5 reanalysis from the AWS Open Data registry | Model features | ERA5 is reanalysis, not a forecast. The 48-hour forecast needs forecast weather for future hours. |
| Road density, land use | OpenStreetMap extract per city | Static geographic features | Compute once per station and per grid point. |
| Time features | Derived | Hour, day of week, month | Captures traffic and seasonal patterns. |
| Active-fire detections | NASA FIRMS | Upwind fire-count feature, supports stubble-burning explanations | Needs a free API key. Confirm access early. |
| Satellite aerosol optical depth | AWS Open Data registry or another public source | Feature | Check coverage and latency. Cloud gaps are expected. |
| Low-cost sensor data | Public low-cost sensor networks if available for the target cities; otherwise a simulated stream replayed from historical station data with injected humidity-dependent bias | Calibration module | Label simulated data as simulated. |
| City registry | Config in S3 or DynamoDB | Bounding box, timezone, station IDs, model settings per city | Drives multi-city support. |

Storage: raw files in S3, cleaned tables in S3 as Parquet, queryable through Athena (Glue catalog optional).

**Data quality rules:** drop physically impossible readings, keep a flag for imputed values, record the data window used, and state it on the evaluation slide.

## 9. Model

- **Task:** regression of PM2.5 at (lat, lon, time), for the present (nowcast) and up to 48 hours ahead (forecast, section 11).
- **Algorithm:** gradient-boosted trees (XGBoost). Chosen for speed, strong tabular performance, and native SHAP support.
- **Features:** weather variables, hour and day features, road density and land-use features at the location, distance-weighted average of nearby station readings at the same hour, distance to nearest station, upwind fire-detection count, and satellite aerosol optical depth where available.
- **Important:** for training, each station's own reading must be excluded from its neighbor features. Otherwise the model leaks the answer.
- **Confidence:** derived from distance to the nearest station and spread of nearby readings, with thresholds set after looking at validation error versus distance. Add quantile models for a prediction interval.

### Evaluation (the core of the pitch)

- **Method:** leave-one-station-out cross-validation. Train without a station, predict it, repeat for every station.
- **Baselines:** (a) nearest-station reading, (b) inverse-distance-weighted average of stations.
- **Metrics:** RMSE and MAE in µg/m³, plus error broken down by distance to nearest station.
- **Reporting rule:** show the real numbers even if the improvement is modest, and state the limits (few stations, short data window). An honest result is better than an inflated one.

## 10. Explainability

1. Compute SHAP values for each prediction (SageMaker Clarify if setup is smooth, otherwise the `shap` library in the same endpoint or Lambda).
2. Select the three features with the largest absolute contribution.
3. Map each feature to a human-readable note via a fixed lookup (for example, low wind speed maps to "low wind trapping pollutants").
4. Send drivers to Bedrock for a single sentence and an advice line, with constraints below.

### Bedrock prompt constraints

- Use only the drivers provided. Do not invent causes such as "stubble burning" unless a feature in the input represents it.
- Describe contributions as "associated with", not as proven causes.
- Keep the explanation to two sentences or fewer and the advice to one sentence.
- Advice must match the AQI category and avoid medical claims beyond general guidance.
- Return JSON only.

## 11. Extended modules

All modules below are in scope. Each reuses the data pipeline, feature tables, and API pattern of the core estimator.

### 11.1 48-hour forecast

- **Model:** gradient-boosted regression per horizon bucket (1-6 h, 7-24 h, 25-48 h) using lagged PM2.5, forecast weather, and the same static features.
- **Evaluation:** MAE and RMSE by horizon against a persistence baseline (last observed value), on a time-based holdout.
- **AWS:** SageMaker for training and inference. EventBridge refreshes forecasts on a schedule and writes them to S3.
- **UI:** horizon chart with intervals, and drivers for the peak hour.

### 11.2 Heatmap grid

- A scheduled job predicts PM2.5 on a regular grid per city and stores it in S3 as a map layer. Cell size is set from the compute budget.
- Cells far from any station are drawn as lower confidence.

### 11.3 Low-cost sensor calibration

- **Problem:** low-cost optical PM sensors read high in humid air and drift over time.
- **Model:** correct raw readings using humidity, temperature, and the raw value against co-located reference readings. Explain corrections with SHAP.
- **Data:** use public low-cost sensor data if available for the target cities. Otherwise replay historical station data through a simulated sensor fleet with injected humidity-dependent bias and noise. No physical hardware is involved either way.
- **Honesty rule:** simulated results demonstrate the pipeline, not real-world accuracy, and are labeled that way everywhere they appear.
- **AWS:** IoT Core (simulated devices over MQTT), Kinesis Data Streams, Lambda, Timestream, SageMaker endpoint, QuickSight.
- **Evaluation:** error before and after calibration against reference readings.

### 11.4 Lowest-exposure route

- **Input:** start, end, and mode (walk, cycle, drive).
- **Method:** request candidate routes from Amazon Location Service, sample points along each, call the estimator at each point and time, and compute mean and cumulative exposure.
- **Output:** ranked routes with time, distance, and exposure, plus the trade-off in plain words and the confidence along the route.
- **Check in hour 1:** whether Location Service returns alternative routes in your region. If not, build alternatives by adding waypoints.

### 11.5 Multi-city

- A city registry (bounding box, timezone, station list, model settings) in config drives data pulls, models, and the map.
- Start with a shared model that has city-level features. Use a separate model per city only if the shared one underperforms.
- Choose cities by measured OpenAQ coverage, not by assumption.

### 11.6 Hindi and audio

- Translate renders the explanation and advice in Hindi. Polly reads it aloud. Audio is cached in S3 per explanation.
- Keep a fixed glossary for AQI terms so wording stays consistent.

### 11.7 Accounts and alerts

- Cognito handles sign-in. Saved places and thresholds live in DynamoDB.
- EventBridge runs a periodic check against the forecast, and SNS sends an email when a threshold is crossed.

### 11.8 Authority dashboard

- A QuickSight dashboard over Athena and S3 shows estimates by area, low-confidence areas, calibration results, and alert counts.

## 12. Architecture

```
Sources (OpenAQ, weather, OSM, FIRMS, AOD) -> S3 raw -> Glue/Athena + SageMaker Processing -> S3 features (Parquet)
                                                        |
        SageMaker training: nowcast, forecast, calibration models (+ Clarify SHAP)
                                                        |
Simulated sensors -> IoT Core -> Kinesis -> Lambda -> Timestream -> calibration endpoint
EventBridge (schedule) -> Lambda -> SageMaker -> S3 (grid layer, forecasts) -> alert check -> SNS
Browser (S3 + CloudFront, Cognito) -> API Gateway -> Lambda -> SageMaker endpoint -> drivers
                                                    |-> Bedrock (explanation, advice) -> Translate -> Polly
                                                    |-> Amazon Location Service (map, routes)
                                                    |-> DynamoDB (users, saved places, cache)
QuickSight over Athena/S3 -> authority dashboard
```

| Layer | AWS service | Responsibility |
| --- | --- | --- |
| Storage and query | S3, Athena, Glue | Raw and processed data, queries |
| Training | SageMaker | Nowcast, forecast, and calibration models |
| Explainability | SageMaker Clarify (or `shap` fallback) | Per-prediction SHAP |
| Inference | SageMaker endpoint (fallback: model file in S3 loaded by Lambda) | Predict PM2.5 |
| Orchestration | Lambda, API Gateway | Request handling and assembly |
| Language | Bedrock, Translate, Polly | Explanation, advice, Hindi text and audio |
| Maps and routes | Amazon Location Service | Map display and route candidates |
| Sensor stream (simulated) | IoT Core, Kinesis, Timestream | Ingest and store simulated sensor readings |
| Scheduling and alerts | EventBridge, SNS | Forecast refresh, grid job, email alerts |
| Accounts and state | Cognito, DynamoDB | Sign-in, saved places, thresholds, cache |
| Analytics | QuickSight | Authority dashboard |
| Hosting | S3 + CloudFront (or Amplify) | Static front end |
| Observability | CloudWatch | Logs and errors |

Region: choose one that supports Bedrock models and SageMaker for your account. Confirm in the first hour.

## 13. API contract

**POST /estimate**

Request:

```json
{ "lat": 28.6139, "lon": 77.2090, "timestamp": "2026-10-10T18:00:00+05:30" }
```

Response:

```json
{
  "pm25": 184.2,
  "category": "Very Poor",
  "confidence": "medium",
  "nearest_station_km": 3.1,
  "drivers": [
    { "feature": "wind_speed", "shap": 32.0, "note": "low wind trapping pollutants" },
    { "feature": "nearby_station_avg", "shap": 28.0, "note": "surrounding stations reading high" },
    { "feature": "hour_of_day", "shap": 11.0, "note": "evening traffic peak" }
  ],
  "explanation": "Plain-language sentence from Bedrock",
  "advice": "One-line advice",
  "explanation_source": "bedrock"
}
```

**GET /stations** returns station id, name, lat, lon, and latest reading for map markers.

**Errors:** return a structured error with a code. If Bedrock fails, return `explanation_source: "fallback"` with template text built from the lookup table.

**Additional endpoints**

- **GET /forecast?lat&lon&hours=48** returns an hourly series with intervals and the drivers for the peak hour.
- **GET /grid?city&timestamp** returns the precomputed grid for the heatmap layer.
- **POST /route** takes start, end, mode, and timestamp, and returns candidate routes with distance, time, mean and cumulative exposure, and a recommended route.
- **POST /calibrate** takes sensor id, raw PM2.5, humidity, temperature, and timestamp, and returns the corrected value with its drivers.
- **GET /cities** returns the city registry.
- **POST /subscriptions** and **GET /subscriptions** (authenticated) manage saved places, thresholds, and the email channel.
- **/estimate** accepts `"lang": "hi"` and `"audio": true`, and then also returns the Hindi text and a presigned URL for the Polly audio.

## 14. Non-functional requirements

- **Latency:** estimate response under about 5 seconds end to end for the demo. Cache repeated requests.
- **Reliability:** every external dependency (Bedrock, SageMaker) has a fallback, and the demo must run without a live call to any third-party API (use pre-pulled data).
- **Security:** least-privilege IAM roles, no keys in the front end, API Gateway throttling on.
- **Cost:** shut down the SageMaker endpoint and notebook instances when not demoing. Set a budget alarm.
- **Honesty:** the UI always shows that values are model estimates, not measurements.

## 15. Team split

**Person A (ML and data):** data pulls and cleaning for all target cities, feature engineering (including fire and aerosol features), nowcast model, leave-one-station-out evaluation, SHAP output, 48-hour forecast model and horizon evaluation, calibration model and simulated sensor stream, model deployment, and the scheduled grid job.

**Person B (AWS plumbing and UI):** account and permissions setup, Bedrock access and prompt, Lambda and API Gateway, Location Service map and routing, Cognito and DynamoDB, alerts through EventBridge and SNS, Translate and Polly, QuickSight dashboard, multi-city config, front end, architecture diagram, and slides.

**Shared:** agree the API contract in the first 30 minutes. Person B builds against a mocked response until the real endpoint is ready.

## 16. Timeline (31 hours, includes sleep)

| Block (elapsed hours) | Work | Exit check |
| --- | --- | --- |
| 0-3 | AWS access, Bedrock, Translate, and Polly access, SageMaker quota request, data pulls started for Delhi and candidate cities, contract agreed, mock end-to-end call | Fake data flows from browser to Lambda and back |
| 3-10 | A: features, nowcast training, leave-one-station-out evaluation. B: map UI, Cognito, DynamoDB, city registry, all against mock data | First RMSE; map and sign-in working |
| 10-16 | Phase 1 integration: real endpoint, SHAP, Bedrock explanation, fallback text, Hindi text and Polly audio, station markers | A click returns a real estimate, explanation, and audio |
| 16-22 | Phase 2. A: 48-hour forecast model, horizon evaluation, fire and aerosol features. B: grid heatmap job, route comparison | Forecast chart, heatmap, and route result live |
| 22-27 | Phase 3. A: calibration model and simulated stream. B: alerts through EventBridge and SNS, authority dashboard, additional cities | Calibration before and after, alert email received, a second city loads |
| 27-31 | Evaluation slides, architecture diagram, demo script, backup recording, rehearsal. Bug fixes only | Backup demo video recorded |

These are elapsed hours and include sleep, so plan for roughly 20 working hours. Every module stays in scope; the order is dependency order, because each later module reuses the pipeline, features, and API of the earlier ones.

**Checkpoints:** at hour 3, continue if station data is in S3 and a basic feature table exists. If data or access is blocked, change the implementation (for example, Lambda inference instead of a SageMaker endpoint, or a different weather source), not the scope. At hour 16, Phase 1 must work end to end before Phase 2 starts.

## 17. Risks and mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Full scope exceeds about 20 working hours for two people | High | Build in dependency order, reuse one pipeline and one Lambda and IAM template across modules, finish each module to a demoable state before starting the next, record a backup demo video early |
| Sparse or gappy station data | High | Hold out whole stations, report honestly, show error by distance |
| SageMaker endpoint quota or setup delays | Medium | Request early. Fallback: load the model file in Lambda |
| Bedrock, Translate, or Polly access not enabled | Medium | Enable in hour 1. Fallback: template explanations |
| Data leakage inflating accuracy | Medium | Exclude the target station from its own neighbor features |
| Forecast weather source limits or missing keys | Medium | Pick the source in hour 1, pre-pull data, cache |
| Simulated sensor results look circular | Medium | Use real low-cost data if any exists. Otherwise label results as a pipeline demonstration |
| Location Service returns no route alternatives | Medium | Build alternatives with waypoints |
| Uneven data coverage across cities | Medium | Choose cities by measured coverage and show confidence accordingly |
| Live demo failure | Medium | Pre-load data, cache responses, record a backup video |

## 18. Success metrics

**Product:** a working click-to-estimate flow for any Delhi point and a selectable hour, with explanation shown every time.

**Technical:** lower leave-one-station-out error than the nearest-station baseline (report the actual percentage), plus a chart of error against distance to nearest station.

**Demo:** under 60 seconds, ending on the evaluation slide. Architecture diagram shows each AWS service doing a distinct job.

**Extended modules:** forecast error beats a persistence baseline at each horizon bucket, calibration reduces error against reference readings (stating whether the data is real or simulated), the route comparison shows an exposure difference and its time cost, an alert email is delivered, and at least two cities load.

## 19. Demo script (about 5 minutes)

1. Problem: "Most Indian streets have no sensor. One station's number is applied to the whole area." (20s)
2. Live: click an area far from any station, show estimate, confidence, and the three reasons. Switch to Hindi and play the audio. (75s)
3. Change the hour, then show the 48-hour forecast chart and the heatmap. (45s)
4. Route comparison between two points: exposure against time. (40s)
5. Calibration module: raw against corrected readings, stating whether the data is real or simulated. (30s)
6. Saved place and alert email, then the authority dashboard and a second city. (30s)
7. Evaluation: model against baselines on unseen stations, forecast by horizon, and the limits. (45s)
8. Architecture slide: what each AWS service does. (30s)
9. Close: where it goes next. (15s)

## 20. Assumptions and open questions

- Assumes enough historical OpenAQ data exists for Delhi to train and validate. Confirm station count and time coverage in hour 1-3.
- Confirm the hackathon's AWS credits, allowed regions, and any restrictions on services.
- Confirm which weather source is fastest to pull and whether it needs an API key.
- Decide the exact time window of data (for example, the most recent few months) based on coverage.
- Confirm submission format: demo video, repo, slides, or all three.

## 21. Priority checklist

Work top to bottom: every tier ends in something demoable and deployable, so whatever is finished when time runs out can be submitted. This order overrides the timeline if you fall behind. A = ML and data, B = AWS and UI.

### Tier 0: Setup (gates everything)

- [ ] (B) Enable Bedrock model access, Translate, and Polly in one region, and confirm it
- [ ] (B) Request SageMaker instance quota, and decide the Lambda-inference fallback now
- [ ] (B) Set a billing alarm and least-privilege IAM roles for both of you
- [ ] (A) Register the OpenAQ API key and the NASA FIRMS MAP\_KEY
- [ ] (A) Pull 6 to 12 months of Delhi PM2.5 from the OpenAQ S3 archive, then count stations and missing hours
- [ ] (A+B) Agree the API contract and the city-registry format, and get a mocked /estimate working from browser to Lambda and back

**Done when:** a mock request flows end to end.

### Tier 1: Core estimate (first demo)

- [ ] (A) Pull and join weather data; build features; exclude each station from its own neighbor features
- [ ] (A) Baselines: nearest-station and inverse-distance average
- [ ] (A) Train XGBoost and deploy it (SageMaker endpoint, or the Lambda fallback)
- [ ] (B) Location Service map with station markers and a time selector
- [ ] (B) Click calls /estimate and the side panel shows PM2.5, category, confidence, and nearest-station distance

**Done when:** clicking any Delhi point returns a real estimate with confidence.

### Tier 2: Explain and prove

- [ ] (A) Leave-one-station-out evaluation against both baselines, plus an error-by-distance chart
- [ ] (A) SHAP top three drivers returned by the endpoint
- [ ] (B) Bedrock explanation and advice with the prompt constraints from section 10
- [ ] (B) Fallback template text if Bedrock fails, and a visible "model estimate" label
- [ ] (B) "How accurate is this?" view with the real numbers and the limits

**Done when:** every click shows reasons, and the evaluation view shows the model against the baselines.

### Tier 3: Submission pack v1 (do not skip)

- [ ] (B) Architecture diagram showing what each AWS service does
- [ ] (B) Slides: problem, live demo, evaluation, architecture, limits
- [ ] (A+B) Record a 3-minute demo video and keep the file safe
- [ ] (B) Deploy the front end on CloudFront and test it from another device and network
- [ ] (A) README with data sources, attribution, and how to run

**Done when:** you could submit right now.

### Tier 4: Hindi text and audio

- [ ] (B) Translate for the explanation and advice, with a fixed glossary for AQI terms
- [ ] (B) Polly audio cached in S3, and a language toggle plus play button in the UI

### Tier 5: 48-hour forecast

- [ ] (A) Forecast features from forecast weather and lagged PM2.5, one model per horizon bucket
- [ ] (A) Evaluate MAE and RMSE by horizon against the persistence baseline
- [ ] (B) /forecast endpoint and a horizon chart with intervals

### Tier 6: Heatmap and extra features (in parallel)

- [ ] (B) Scheduled grid job writing a map layer to S3, with low-confidence cells drawn differently
- [ ] (A) Fire-count and aerosol features, if the data pulls cleanly, with their drivers added to the explanation lookup

### Tier 7: Lowest-exposure route

- [ ] (B) Check whether Location Service returns route alternatives in your region, else build them with waypoints
- [ ] (B) Sample points along each route, call the estimator, and rank by cumulative exposure
- [ ] (B) UI showing time against exposure for each route

### Tier 8: Accounts and alerts

- [ ] (B) Cognito sign-in, and saved places and thresholds in DynamoDB
- [ ] (B) EventBridge check against the forecast, with SNS email alerts and a tested alert email

### Tier 9: Sensor calibration

- [ ] (A) Look for real public low-cost sensor data first; otherwise build the simulated stream
- [ ] (A) Calibration model with SHAP, and error before and after against reference readings
- [ ] (B) IoT Core, Kinesis, Timestream path for the simulated stream, and a before/after view labeled real or simulated

### Tier 10: Multi-city

- [ ] (A) Check OpenAQ coverage and choose cities from the data
- [ ] (A+B) Add each city to the registry, run its pull, and check the shared model per city
- [ ] (B) City selector in the UI

### Tier 11: Authority dashboard

- [ ] (B) QuickSight over Athena and S3: estimates by area, low-confidence areas, calibration results, alert counts

### Tier 12: Final refresh (hours 27 to 31)

- [ ] (A+B) Freeze: no new modules
- [ ] (A+B) Update the slides and diagram with only the tiers that work, using measured numbers only
- [ ] (A+B) Re-record the demo video and rehearse twice
- [ ] (A+B) Final deploy check from a clean browser

### Rules that make partial delivery work

- After each tier: deploy, smoke test, and record a short clip of the new feature.
- Hide anything unfinished from the UI instead of showing it broken.
- If a tier is half done at the freeze, ship the finished part and remove the rest from the slides.
- Report only real results. Label simulated data as simulated everywhere.
