# Design: UI and UX Specification

Explainable Street-Level AQI, Environmental Hacks (DTU). Light theme only.

This document tells you how the interface should look and behave. It follows the PRD (what is built), the architecture (what each screen calls), the rules (honesty and submission-first), and the phases (what ships when). Tier numbers refer to the priority checklist in the PRD.

## 1. Design principles

1. **Core first.** The default screen is the core: map, one click, an estimate, the reasons. Extras never crowd it. If an extra is off, it is absent, not greyed out.
2. **Honest by design.** Every number is labeled as a model estimate, confidence is always visible, and simulated data is always labeled. Design makes the limits easy to see, not hidden.
3. **Explain before you decorate.** The reasons for a reading get as much visual weight as the reading itself.
4. **Readable at a glance.** A resident should understand "how bad, why, what do I do" in under five seconds.
5. **Light and calm.** Light backgrounds, restrained color, color used mainly for air-quality category. No dark panels.
6. **Works on a phone.** Many users will open this on a phone, so the mobile layout is designed in parallel, not after.
7. **Never broken-looking.** Every state (loading, error, fallback, low confidence, no data) has a designed appearance.

## 2. Visual foundation

### 2.1 Color tokens (light theme)

Define these as CSS variables on `:root`. Do not add a dark mode.

| Token | Value | Use |
|---|---|---|
| `--bg-page` | `#F7F8FA` | Page background |
| `--bg-surface` | `#FFFFFF` | Panels, cards, bottom sheet |
| `--bg-subtle` | `#F0F3F7` | Inputs, chips, table stripes |
| `--bg-hover` | `#E9EEF4` | Hover and pressed states |
| `--border` | `#E3E7ED` | Dividers, card outlines |
| `--text` | `#1B2430` | Primary text |
| `--text-muted` | `#5B6675` | Secondary text, captions |
| `--accent` | `#0F766E` | Primary buttons, links, focus accents |
| `--accent-tint` | `#E3F3F1` | Selected states, accent backgrounds |
| `--info-tint` | `#E8F0FE` | Informational notes |
| `--sim-tint` | `#F3EEFB` | "Simulated data" labels |
| `--sim-text` | `#5B3E96` | Text on simulated labels |
| `--focus` | `#1F6FEB` | Keyboard focus ring |
| `--error-tint` | `#FDE8E4` | Error banners |
| `--error-text` | `#A12A18` | Error text |

### 2.2 Air-quality category colors

Show the category as a **name plus a color**, never color alone. Each category has a map fill, a light tint for backgrounds, and a dark text color for use on the tint.

| Category | PM2.5 band (µg/m³) | Fill | Tint | Text on tint |
|---|---|---|---|---|
| Good | 0-30 | `#3FA45B` | `#E8F5EC` | `#1E6B3A` |
| Satisfactory | 31-60 | `#8DBF3F` | `#F1F7E3` | `#4F6B1A` |
| Moderate | 61-90 | `#E8C220` | `#FDF6D8` | `#7A5F00` |
| Poor | 91-120 | `#F08A24` | `#FEEFDD` | `#8A4A06` |
| Very Poor | 121-250 | `#E04F39` | `#FDE8E4` | `#A12A18` |
| Severe | above 250 | `#9B2257` | `#F9E6EE` | `#7A1744` |

Verify these bands against the official CPCB table before shipping, and check every text and tint pair with a contrast checker (target 4.5:1 for normal text).

### 2.3 Confidence colors

Confidence is **not** a category color. Use neutral tones so it never competes with the air-quality color.

| Level | Style |
|---|---|
| High | Filled dot and label, `--text` |
| Medium | Half-filled dot and label, `--text` |
| Low | Hollow dot, label, plus a dashed outline on the estimate card |

### 2.4 Typography

| Role | Font | Size and weight |
|---|---|---|
| Interface | Inter, falling back to system sans | Base 16 px |
| Hindi | Noto Sans Devanagari | Same sizes, line height 1.6 |
| Numbers | Inter with tabular figures | Use `font-variant-numeric: tabular-nums` |

| Style | Size | Weight |
|---|---|---|
| Hero value (PM2.5) | 48 px (36 px on mobile) | 700 |
| Category label | 20 px | 600 |
| Section heading | 16 px | 600 |
| Body | 16 px | 400 |
| Caption and labels | 13 px | 400, `--text-muted` |

### 2.5 Spacing, shape, elevation

- Spacing scale: 4, 8, 12, 16, 24, 32, 48.
- Radius: 12 px for cards and panels, 8 px for inputs and buttons, full for chips.
- Elevation: one soft shadow for floating elements (`0 2px 12px rgba(27,36,48,0.08)`), plus 1 px `--border` outlines. No heavy shadows.
- Icons: a single outline icon set, 20 px, stroke 1.75.

### 2.6 Map styling

- Use a **light basemap style** from Amazon Location Service. Keep roads and labels muted so category colors stand out.
- Station markers: white circle with a colored ring in the category color of its latest reading, plus a small label on zoom.
- Selected point: a pin with a soft halo; the panel opens at the same time.
- Heatmap layer (when on): semi-transparent category colors at about 55% opacity, with low-confidence cells drawn with a diagonal hatch.
- Route lines (when on): 4 px lines; the recommended route in `--accent`, alternatives in a neutral grey.
- MapLibre GL JS is the usual renderer for Location Service maps; confirm in the current SDK docs.

## 3. Layout

### 3.1 Breakpoints

| Name | Width | Layout |
|---|---|---|
| Mobile | below 640 px | Full-screen map, bottom sheet for the panel |
| Tablet | 640-1023 px | Map with a 360 px side panel |
| Desktop | 1024 px and up | Map with a 400 px side panel; evaluation view as a full page |

### 3.2 Desktop wireframe (core, Tiers 1-2)

```
+----------------------------------------------------------------------------+
| AQI Delhi ▾ (city)        [Search place]          [EN | हिं]   [Sign in]  |
+--------------------------------------------------+-------------------------+
|                                                  |  Estimated PM2.5        |
|                                                  |  184 µg/m³              |
|               LIGHT MAP                          |  [ Very Poor ]          |
|          o station   o station                   |  ● ● ○ Medium confidence|
|                  ◉ selected point                |  Nearest station 3.1 km |
|                                                  |-------------------------|
|                                                  |  Why                    |
|                                                  |  Low wind and high      |
|                                                  |  readings nearby are    |
|                                                  |  associated with...     |
|                                                  |  Wind speed     ████ +32|
|                                                  |  Nearby avg     ███  +28|
|                                                  |  Hour of day    █    +11|
|                                                  |-------------------------|
|                                                  |  What to do             |
|                                                  |  Limit outdoor exercise.|
|                                                  |  [▶ Listen]             |
|                                                  |-------------------------|
|  Time: [ ◀ 18:00, 10 Oct ▶ ]  [Now]             |  Model estimate, not a  |
|                                                  |  measurement. How       |
|                                                  |  accurate is this? →    |
+--------------------------------------------------+-------------------------+
```

### 3.3 Mobile wireframe

```
+------------------------------+
| AQI Delhi ▾        EN | हिं  |
|  [Search place]              |
|                              |
|        LIGHT MAP             |
|     o        ◉               |
|                              |
|  [◀ 18:00 ▶]  [Now]          |
+------------------------------+
|  ───  (drag handle)          |
|  184 µg/m³   [ Very Poor ]   |
|  ● ● ○ Medium · 3.1 km       |
|  Why: low wind and high      |
|  readings nearby ...         |
|  [ Details ▾ ]               |
+------------------------------+
```

The bottom sheet has three heights: **peek** (value, category, confidence), **half** (adds reasons and advice), **full** (adds driver chart, audio, and links to accuracy and forecast).

## 4. Screens and flows

| # | Screen | Purpose | Calls | Tier |
|---|---|---|---|---|
| 1 | Map and estimate | Core experience | `GET /stations`, `POST /estimate` | 1-2 |
| 2 | Accuracy view | Evidence for judges and curious users | Static evaluation outputs | 2 |
| 3 | Language and audio | Hindi explanation and playback | `POST /estimate` with `lang`, `audio` | 4 |
| 4 | Forecast tab | 48-hour outlook | `GET /forecast` | 5 |
| 5 | Heatmap layer | Area overview | `GET /grid` | 6 |
| 6 | Route planner | Lowest-exposure route | `POST /route` | 7 |
| 7 | Saved places and alerts | Personal thresholds | `GET/POST /subscriptions` | 8 |
| 8 | Calibration view | Raw vs corrected sensor readings | `POST /calibrate` | 9 |
| 9 | City selector | Switch city | `GET /cities` | 10 |
| 10 | Authority dashboard | Officer overview | QuickSight embed | 11 |

### 4.1 Core flow (Screens 1 and 2)

1. User lands on the map with station markers and the latest hour selected. A short hint reads "Tap anywhere on the map for an estimate."
2. User taps a point. A pin appears and the panel opens in a loading state (skeleton blocks, no spinner-only screens).
3. Panel fills in this order: value and category, confidence and nearest-station distance, reasons, advice.
4. User changes the hour with the time selector. The panel updates in place and keeps scroll position.
5. User opens "How accurate is this?" to see the evaluation view.

### 4.2 Accuracy view (Screen 2)

A full page on desktop, a full-height sheet on mobile.

- A one-sentence headline with the real result, for example "On stations the model never saw, error was X µg/m³ compared with Y for the nearest-station method." Fill with measured numbers only.
- Bar chart: model vs nearest-station vs inverse-distance baselines.
- Line or bar chart: error against distance to the nearest station.
- A "Limits" block in plain words: number of stations, data window, gaps.
- When forecast and calibration exist, add sections for error by horizon and error before and after calibration. Calibration results carry the simulated label if data is simulated.

### 4.3 Extras

Each extra opens as a tab or mode inside the same screen, never as a separate maze of pages.

- **Forecast (Tier 5):** a tab in the panel with a line chart for 48 hours, a shaded band for the interval, and a marker at the peak. Tapping the peak shows its drivers.
- **Heatmap (Tier 6):** a toggle on the map ("Show area view"). A small legend explains the colors and the hatch for low-confidence cells.
- **Route (Tier 7):** a "Route" button opens two fields (from, to) and a mode selector (walk, cycle, drive). Results appear as cards: time, distance, exposure, with the recommended one marked. A plain sentence explains the trade-off, for example "Takes 4 minutes longer, with about N% less exposure."
- **Saved places and alerts (Tier 8):** "Save this place" in the panel prompts sign-in, then a threshold picker (by category, not a raw number) and an email toggle. A list view shows saved places with their current category.
- **Calibration (Tier 9):** a page with raw reading, corrected reading, and the drivers of the correction. A purple "Simulated data" banner is shown whenever the stream is simulated.
- **City selector (Tier 10):** a dropdown in the header listing available cities; changing it recenters the map.
- **Dashboard (Tier 11):** an officer page opened from a menu entry; the embedded dashboard sits inside the same header and light layout.

### 4.4 Language toggle (Tier 4)

- A two-option toggle in the header: EN and हिं.
- Switching language re-renders the explanation and advice in Hindi; numbers and category names stay clear and consistent using the fixed glossary.
- The "Listen" button plays the Hindi audio when Hindi is selected, and shows a small loading state while the audio is prepared.

## 5. Components

| Component | Content | Notes |
|---|---|---|
| Estimate card | PM2.5 value, unit, category chip, "Model estimate" caption | Category tint as card background; low confidence adds a dashed outline |
| Confidence badge | Dot indicator, label, one-line reason such as "nearest station 6.2 km away" | Neutral colors only |
| Driver list | Top three drivers: name, direction, bar, SHAP value, one short note | Bars in a single neutral accent, not category colors |
| Explanation card | Up to two sentences from Bedrock, "associated with" wording | Shows a small "Template" tag if the fallback was used |
| Advice line | One sentence matched to the category | Placed under its own heading "What to do" |
| Time selector | Previous, next, current time, and a "Now" button | Disabled at the edges of the data window |
| Station marker | Ring in category color, label on zoom | Tap shows reading and time |
| Legend | Six category swatches with names and bands | Collapsible on mobile |
| Chart | Line, bar, interval band | Axis labels with units, light gridlines, one accent color plus neutrals |
| Banners | Info, simulated, error | Tinted backgrounds from the token table |
| Empty and error states | Illustration-free: icon, one sentence, one action | See section 6 |
| Feature entry points | Tabs or buttons shown only when the feature flag is on | Absent, not disabled, when off |

## 6. States

| State | Appearance |
|---|---|
| Initial | Map with markers, hint text, empty panel prompt |
| Loading | Skeleton blocks in the panel in the final layout; the pin is already placed |
| Success | Full panel as in the wireframe |
| Low confidence | Dashed card outline, "Low confidence" badge, and a note "Few stations nearby. Treat this as a rough estimate." |
| Fallback explanation | Same layout; small "Template" tag on the explanation |
| Outside coverage | The point is outside the city boundary: "No estimate here yet. Try a point inside the shaded area." with the city boundary outlined |
| No data for the hour | "No data for this hour. Try an earlier time." with a one-tap jump to the latest available hour |
| Error | Light red banner with a short message and a "Try again" button; the previous estimate stays visible if one exists |
| Offline | Banner "You're offline." Cached results stay visible |
| Audio loading or failed | Button shows a small loader, then reverts with "Audio unavailable" on failure |
| Feature off | The control does not appear |

## 7. Content and tone

Follow the honesty rules in `rules.md`. Plain language, no jargon, no alarmism.

| Do | Don't |
|---|---|
| "Estimated PM2.5" | "PM2.5 is" |
| "Low wind is associated with higher readings" | "Low wind causes the pollution" |
| "Model estimate, not a measurement" | Presenting the value as measured |
| "Simulated data" on anything from the simulated stream | Leaving the label off |
| "Few stations nearby, so this is a rough estimate" | Hiding uncertainty |
| "Limit outdoor exercise" | Medical claims or diagnoses |

Advice lines by category (keep to one sentence, general guidance only):

| Category | Advice |
|---|---|
| Good, Satisfactory | "Air quality is acceptable for most outdoor activity." |
| Moderate | "Sensitive groups may want to limit long outdoor exertion." |
| Poor | "Limit prolonged outdoor activity, especially for children and older adults." |
| Very Poor | "Avoid outdoor exercise. Sensitive groups should stay indoors." |
| Severe | "Stay indoors where possible and avoid outdoor activity." |

Have the wording reviewed, and keep Bedrock's output within these meanings.

## 8. Motion

- Short and quiet: 150-200 ms fades and slides.
- The panel slides in from the right on desktop and up from the bottom on mobile.
- Skeleton blocks pulse gently while loading.
- Respect `prefers-reduced-motion`: replace slides and pulses with instant changes.

## 9. Accessibility

- Text contrast at least 4.5:1 on its background; check every category pair.
- Category is always shown by name as well as color. Heatmap hatching and marker labels cover users who cannot distinguish colors.
- Full keyboard use: tab order is header, search, map controls, time selector, panel. The map point can also be chosen by entering a place in search.
- Visible focus ring in `--focus`, 2 px, offset 2 px.
- Touch targets at least 44 by 44 px.
- Charts have a text summary for screen readers and a "View data" table toggle.
- Hindi text uses a proper Devanagari font, with lang attributes set so screen readers pronounce it correctly.
- The audio button has a text label and a state ("Playing", "Paused").

## 10. Implementation notes

- Static front end on S3 and CloudFront; plain HTML, CSS, and JavaScript or a small framework. Keep dependencies few so builds are fast.
- Put all colors and spacing in CSS variables from section 2 so changes are one edit.
- Feature flags: one config object read at startup. Controls for flags that are off are not rendered.
- Cache the last response per point and hour so toggling language or time feels instant, matching the response cache in the architecture.
- Call only the endpoints in the architecture document. No keys in the front end.
- Keep the map rendering on one canvas, and update layers rather than recreating the map.
- Pre-render the evaluation view from saved outputs so it never depends on a live service.

## 11. Mapping to phases

| Phase | Screens and components that must be done |
|---|---|
| 1 | Static page with mock `/estimate`, header, empty map |
| 2 | Screens 1 and 2, all core components, all core states, legend, light map style, mobile bottom sheet |
| 3 | Screens 3 to 10, each behind its feature flag, in checklist order |
| 4 | Visual polish, accessibility pass, final screenshots for slides, removal of unfinished entry points |

## 12. UI acceptance checklist

- [ ] Light backgrounds everywhere; no dark panels or dark map
- [ ] Core flow works on a phone and a desktop browser
- [ ] Value, category, confidence, reasons, and advice all visible without scrolling on desktop
- [ ] "Model estimate" caption visible on every estimate
- [ ] Simulated data labeled wherever it appears
- [ ] Every category shown by name and color, with legend
- [ ] All states in section 6 designed and tested, including fallback and low confidence
- [ ] Contrast checked for every text and background pair
- [ ] Keyboard navigation and focus rings work
- [ ] Hindi renders correctly and audio plays
- [ ] Controls for unfinished features are absent
- [ ] Screenshots captured for the slides and README
