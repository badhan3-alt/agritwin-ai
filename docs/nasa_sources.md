# Climate sources, assumptions, and limits

## Bangladesh district locations

The farm selector covers all 64 districts under the 8 divisions, with English and Bengali names. Membership is checked against the [Bangladesh National Portal district list](https://bangladesh.gov.bd/views/district-list/District-List/). Approximate district headquarters coordinates come from [Bangladesh GeoCode](https://github.com/nuhil/bangladesh-geocode), with its MIT license preserved at `farms/data/BANGLADESH_GEOCODE_LICENSE.txt`. Five existing city reference points are retained; the bundled dataset records these modifications. Coordinates are rounded to four decimals to match the form inputs.

These points help choose a starting location. They are not district boundary centroids or measurements of every farm in a district. Select the actual field coordinates for a location-specific NASA request. District selection does not supply soil texture, pH, drainage, or salinity values.

## Implemented integration: NASA POWER

The application retrieves monthly historical climate information from NASA POWER's point climatology endpoint:

```text
https://power.larc.nasa.gov/api/temporal/climatology/point
```

Requests include the selected latitude and longitude, the agricultural community, a fixed parameter list, and JSON output. See the [official POWER climatology API documentation](https://power.larc.nasa.gov/docs/services/api/temporal/climatology/) for the endpoint and request format.

The implementation reads the response metadata rather than claiming that every response covers a fixed reference period. Provenance is stored with the analysis and remains available in the dashboard and report. POWER's returned period can change as the service updates its climatology.

| Parameter | Use in AgriTwin AI |
| --- | --- |
| `T2M` | Monthly mean air-temperature screening |
| `T2M_MAX` | Monthly maximum-temperature screening |
| `T2M_MIN` | Monthly minimum-temperature context |
| `PRECTOTCORR` | Monthly precipitation totals and seasonal water screening |
| `GWETROOT`, when available | Relative root-zone wetness context, without claiming a volumetric measurement |

POWER values are regional gridded data. A coordinate selects a grid location; it does not provide a separate sensor measurement for a small farm or prove uniform conditions across the field. Meteorological and wetness products can include model/reanalysis information; see [POWER meteorological data sources](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/). The UI therefore describes the source as a regional climate product.

### Units and missing values

The service uses response parameter metadata to interpret precipitation units. A daily rate is multiplied by climatological month length to obtain a monthly amount, using 28.25 days for February. A monthly total is not multiplied again. Units are never inferred from whether a precipitation number happens to be less than a threshold.

Fill values, invalid numbers, incomplete required month series, and unexpected payloads cause a NASA-data-unavailable error. The service does not replace them with synthetic climate values. Optional missing wetness information remains unavailable.

Monthly climatological maximum temperatures are not daily extremes. A month crossing the prototype's heat-screening threshold does not establish the number of hot days, the exact flowering period, or a quantified yield loss.

## NASA availability, original data, and caching

Real NASA data is mandatory. Network failures, timeouts, rate limits, or unusable responses raise an unavailable-data error; they never produce synthetic climate observations. The farm profile remains available. Without a valid NASA baseline, climate analysis, rotation scoring, scenario simulation, and report generation remain unavailable, with a retry action.

The Rajshahi example farm also retrieves NASA POWER data. It does not bypass the NASA requirement. Old synthetic analyses are ignored and must be replaced with a valid NASA retrieval before analysis pages can use them.

The climate service caches valid NASA responses for six hours through Django's local-memory cache. Failures can be remembered briefly to avoid repeating an unavailable request on every page visit, but are never treated as climate data. A refresh bypasses the service cache. Saved analyses retain their original NASA provenance; reading a saved response is not a fresh retrieval. If a refresh fails, the prior valid NASA snapshot is retained, with its original retrieval time visible.

Each successful analysis preserves the original NASA JSON response in addition to the normalized monthly series. The dashboard and report link to the NASA request URL and provide an original-response download. The download is the historical climatology used by that analysis, not a new request or a real-time weather observation.

## Not integrated

| Source | Current status |
| --- | --- |
| NASA SMAP | No authenticated retrieval, ingestion, or gridded-file processing is implemented |
| GPM IMERG | Not connected |
| Landsat / HLS | Not connected |
| Farm laboratory measurements | Entered by the farmer when known; not inferred from satellite data |
| Local crop market feeds | Not connected; economic scoring is a prototype heuristic |

POWER relative wetness is not relabelled as SMAP. The application does not fabricate volumetric surface or root-zone soil moisture by rescaling a relative wetness value. It also cannot derive field-specific pH or N-P-K nutrient concentrations from the implemented climate data.

## Agricultural assumptions

The crop profiles are a small Bangladesh-focused prototype knowledge base. Planting windows, durations, representative water demand, soil preferences, and component scores are simplifying assumptions and vary with cultivar, soil, management, and local weather. They require review before use for planting decisions. [BAMIS crop calendars](https://www.bamis.gov.bd/en/calendar) are a reference for local calendar review; their inclusion as a reference does not certify this prototype's crop profiles.

Water-demand comparisons describe the profile assumptions; they do not estimate a measured pumping reduction on the selected farm. Nitrogen-fixing crops can contribute to soil-health planning, but the application does not measure nitrogen fixation or calculate a guaranteed fertilizer credit.

The Bangladesh crop calendars are not automatically valid elsewhere. The farm form restricts coordinates to a coarse Bangladesh planning envelope, and the scoring service independently checks the supported area. The envelope is not a verified country boundary or a farm polygon.

## Scenario interpretation

A rainfall or temperature slider changes the stored baseline as a sensitivity test. It is not a future climate projection, a seasonal outlook, or a crop-yield forecast. Source uncertainty and missing farm data remain relevant after the scenario is applied.

The suitability score expresses a relative ranking under these assumptions. It is not a probability, a recommendation certified by NASA, or a promise of profit or yield.
