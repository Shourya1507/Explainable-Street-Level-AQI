# Project Rules

Explainable Street-Level AQI, Environmental Hacks (DTU). Two people, about 31 hours, AWS-first, no hardware.

These rules exist for one reason: **we must be able to submit a good project at any moment, even if none of the extra features get built.** Read them at the start, and re-read rule 1 whenever you are tempted to start something new.

## 1. Submission first

1. The core is the product: click a point, get a PM2.5 estimate, a confidence level, the top three reasons, and one line of advice, backed by validation against baselines. Everything else is an extra.
2. The submission pack (architecture diagram, slides, demo video, deployed URL, README) is built right after the core works (Tier 3 of the checklist), before any extra feature.
3. After that, every extra is added on top of a project that is already submittable. If time runs out, we submit what we have.
4. The main branch is always deployable. Never merge something that breaks the core flow.
5. A half-built extra is worse than no extra. Finish it to a demoable state or hide it.

## 2. Priority order

Work in this order and do not skip ahead. The full task list is the priority checklist in the PRD.

| Tier | What | Submittable after this? |
|---|---|---|
| 0 | Setup, keys, data pull, mocked end-to-end call | No |
| 1 | Core estimate with map and confidence | Barely |
| 2 | SHAP explanations, Bedrock text, evaluation vs baselines | Yes, the minimum good submission |
| 3 | Submission pack v1 | Yes, ready to submit |
| 4-11 | Hindi and audio, forecast, heatmap, routes, alerts, calibration, multi-city, dashboard | Each one adds value |
| 12 | Final refresh and freeze | Final |

Rules for moving between tiers:

- Do not start a tier until the previous one meets its "done when" line.
- Two tiers may run in parallel only if one person owns each and they do not share files.
- If a tier is blocked for more than an hour, change the implementation approach (for example, Lambda inference instead of a SageMaker endpoint) before changing the scope.

## 3. Freeze

- **Hour 27: feature freeze.** No new modules after this point.
- Hours 27 to 31 are for bug fixes, the final slides and diagram, re-recording the demo, and rehearsal.
- At the freeze, anything unfinished is hidden from the UI and removed from the slides. Do not mention it as a feature.
- Leave at least 3 hours before the deadline for submission itself. Submission portals fail, uploads are slow, and videos need re-encoding.

## 4. Honesty rules

These matter more than any feature, because judges ask follow-up questions.

1. Report only measured numbers. Never estimate or round up a result for the slides.
2. Always show the baseline next to the model. If the improvement is small, say so.
3. State the limits openly: few stations, short data window, gaps in the data.
4. Anything built on simulated data is labeled "simulated" in the UI, slides, README, and demo. No exceptions.
5. The UI always says values are model estimates, not measurements.
6. Explanations describe drivers as "associated with", never as proven causes. Do not name a cause (for example, stubble burning) unless a feature in the model actually represents it.
7. If an extra is half done, the README says "partial" or "not built". Never describe a feature that does not work.

## 5. Correctness rules for the model

1. **No leakage.** A station's own reading must never be part of its own neighbor features. Check this first if results look too good.
2. Validate on whole stations that were left out of training, not on random rows.
3. Use a time-based holdout for the forecast, never a random split.
4. Keep the same feature code for training and for serving, so the two cannot drift apart.
5. Record the data window, the station list, and the date of the pull next to every evaluation result.
6. If the model beats the baseline by a suspiciously large margin, assume a bug and investigate before presenting it.

## 6. Working agreements

**Roles.** Person A owns ML and data. Person B owns AWS plumbing and UI. Anything that crosses the line (the API contract, the feature list) is agreed by both before it changes.

**API contract.** It is fixed in the first 30 minutes. Changes need both people to agree and a note in the repo. Person B builds against a mock until the real endpoint exists.

**Branches and commits.**

- Short-lived branches, one per task. Merge to main when it works and the core flow still passes.
- Small commits with clear messages. Commit before switching tasks.
- Never commit keys, credentials, or raw datasets.

**Check-ins.**

- A 5-minute sync every few hours: what is done, what is blocked, what is next.
- At hour 3 and hour 16, run the checkpoint from the PRD out loud: is the core working, and is the plan still realistic?

**Decisions.** If two options are close, pick the simpler one and move on. Write the choice and the reason in one line in the README or a notes file.

## 7. AWS rules

1. Use one region for everything. Choose it in Tier 0 after confirming Bedrock, Translate, Polly, and SageMaker availability.
2. Set a billing alarm in the first hour.
3. Stop SageMaker endpoints and notebook instances whenever you are not testing or demoing.
4. Each Lambda gets its own least-privilege IAM role. No wildcard admin permissions.
5. Keys (OpenAQ, FIRMS) live in Secrets Manager or encrypted environment variables, never in the front end or the repo.
6. Call OpenAQ from backend jobs only, never from the browser.
7. Every service in the architecture diagram must do real work. Do not add a service just to lengthen the list.
8. Every external dependency has a fallback (see the architecture document). Test the fallback at least once.
9. Do not use SMS to Indian numbers. It needs telecom registration. Use email alerts.

## 8. Quality bar for the demo

- The core flow works on a clean browser, on a different network, with no logged-in AWS console.
- Response time for `/estimate` is a few seconds at most. Pre-warm the endpoint and use the cache before demoing.
- Every demo step works from cached or pre-pulled data, with no dependence on a live third-party API.
- A backup demo video exists and is stored in two places.
- Every number on the slides can be traced to a saved evaluation output.

## 9. Scope control

- New ideas go into a "later" list, not into the build.
- Before starting anything not in the checklist, ask: does this make the core better, or is it an extra? If it is an extra, it goes behind the tiers.
- Polish the core before adding an extra. A clean, fast, well-explained core beats a feature-rich project that is flaky.
- Do not rewrite working code to make it prettier after the freeze.

## 10. Submission checklist

Complete this before the deadline, whatever tier you reached.

- [ ] Deployed URL works from a clean browser and another network
- [ ] Demo video recorded (about 3 minutes) and backed up
- [ ] Slides finished: problem, live demo, evaluation, architecture, limits
- [ ] Architecture diagram matches what is actually deployed
- [ ] README lists what is implemented, what is partial, and what is not built
- [ ] README credits data sources (OpenAQ and its original providers, Open-Meteo, OpenStreetMap, NASA FIRMS if used)
- [ ] Simulated data is labeled everywhere it appears
- [ ] Evaluation numbers in the slides match the saved outputs
- [ ] No keys, credentials, or private data in the repo
- [ ] SageMaker endpoints and other billable resources handled according to the hackathon's rules
- [ ] Submission form filled in and confirmed received, with a screenshot saved

## 11. If things go wrong

| Situation | What to do |
|---|---|
| Station data is far sparser than expected | Keep the plan, report the sparsity honestly, show error by distance to the nearest station |
| SageMaker is blocked | Switch to Lambda inference with the model file in S3 |
| Bedrock is blocked | Use template explanations from the driver lookup |
| An extra is not working near the freeze | Hide it, remove it from the slides, and spend the time on the core and the submission pack |
| One of us is stuck for over an hour | Stop and swap tasks or pair on it. Do not silently lose half a day |
| Demo breaks right before judging | Fall back to the recorded video and cached responses |
