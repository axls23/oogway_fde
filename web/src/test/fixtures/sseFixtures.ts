/**
 * Raw SSE fixture streams, byte-for-byte in the wire format described by
 * contracts/sse-frames.schema.json (event: <name>\ndata: <json>\n\n).
 *
 * Used by:
 *  - src/sse/parser.test.ts to verify the parser against realistic sequences
 *  - src/mocks/server.ts to drive the dev-mode mock backend
 *  - component tests for streaming rendering, citations, abstention, and
 *    staged progress
 */

/** F1: grounded Q&A. Citations arrive interleaved with tokens, before the
 * message finishes streaming — this is the behavior design.md §3 requires
 * ("the user sees sources accumulate, not appear all at once at the end"). */
export const SSE_GROUNDED_QA = `event: stage
data: {"stage":"retrieving","detail":null}

event: citation
data: {"chunk_id":8412,"episode":"Product-Market Fit, Pricing, and the Truth About Growth","guest":"Brian Chesky","rank":1,"score":0.82}

event: citation
data: {"chunk_id":8413,"episode":"Product-Market Fit, Pricing, and the Truth About Growth","guest":"Brian Chesky","rank":2,"score":0.77}

event: stage
data: {"stage":"thinking","detail":null}

event: token
data: {"text":"Product-market fit is"}

event: token
data: {"text":" less a single moment and more a threshold you cross when"}

event: token
data: {"text":" retention curves flatten out. Brian Chesky described it as the point where"}

event: token
data: {"text":" you can't make product worse fast enough to lose your growth rate.\\n\\n"}

event: citation
data: {"chunk_id":9021,"episode":"Growth Levers Nobody Talks About","guest":"Elena Verna","rank":3,"score":0.69}

event: token
data: {"text":"Elena Verna adds that pricing experiments only make sense once"}

event: token
data: {"text":" that threshold is crossed, not before."}

event: done
data: {"message_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","latency_ms":2140,"abstained":false}

`;

/** F5: corpus miss. No citation frames — retrieval never returned anything
 * above the relevance floor, so the request short-circuits (architecture.md
 * §7 step 5) and the templated refusal streams as ordinary tokens. The UI
 * distinguishes this state via done.data.abstained, not by parsing text. */
export const SSE_ABSTENTION = `event: stage
data: {"stage":"retrieving","detail":null}

event: token
data: {"text":"Lenny's Podcast doesn't cover this directly."}

event: token
data: {"text":" Closest topics indexed: pricing strategy, activation design, and onboarding."}

event: done
data: {"message_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","latency_ms":410,"abstained":true}

`;

/** F3: Ship 30 essay, staged progress. Stage frames replace in place
 * (design.md: "Drafting section 3 of 6…" updates, does not stack) and an
 * `artifact` frame announces the assembled document once drafting ends. */
export const SSE_SHIP30_ESSAY = `event: stage
data: {"stage":"retrieving","detail":null}

event: citation
data: {"chunk_id":1201,"episode":"Onboarding That Doesn't Suck","guest":"Lenny Rachitsky","rank":1,"score":0.74}

event: citation
data: {"chunk_id":1305,"episode":"The Activation Metric Trap","guest":"Casey Winters","rank":2,"score":0.71}

event: stage
data: {"stage":"outlining","detail":null}

event: stage
data: {"stage":"drafting","detail":"section 1 of 6"}

event: token
data: {"text":"# Why Activation Beats Acquisition\\n\\n## The hook\\n\\n"}

event: token
data: {"text":"Most teams optimize the wrong end of the funnel.\\n\\n"}

event: stage
data: {"stage":"drafting","detail":"section 2 of 6"}

event: citation
data: {"chunk_id":1310,"episode":"The Activation Metric Trap","guest":"Casey Winters","rank":3,"score":0.68}

event: token
data: {"text":"## Section 1: Define the aha moment\\n\\nCasey Winters argues teams should"}

event: token
data: {"text":" work backward from retention, not forward from signup.\\n\\n"}

event: stage
data: {"stage":"drafting","detail":"section 3 of 6"}

event: token
data: {"text":"## Section 2: Instrument before you optimize\\n\\n"}

event: stage
data: {"stage":"drafting","detail":"section 4 of 6"}

event: token
data: {"text":"## Section 3: The second onboarding step tax\\n\\n"}

event: stage
data: {"stage":"drafting","detail":"section 5 of 6"}

event: token
data: {"text":"## Section 4: What Lenny Rachitsky changed at Airbnb\\n\\n"}

event: stage
data: {"stage":"drafting","detail":"section 6 of 6"}

event: token
data: {"text":"## Takeaway\\n\\nActivation is the metric that predicts everything downstream.\\n"}

event: stage
data: {"stage":"assembling","detail":null}

event: artifact
data: {"artifact_id":"a1b2c3d4-e5f6-4789-a0b1-c2d3e4f5a6b7","kind":"markdown","title":"Why Activation Beats Acquisition"}

event: done
data: {"message_id":"b2c3d4e5-f6a7-4890-b1c2-d3e4f5a6b7c8","latency_ms":41230,"abstained":false}

`;

/** Provider error with a partial answer — architecture.md §9/ADR-005 and
 * design.md's "Response was cut off" state. The already-streamed text must
 * remain visible, not be discarded. */
export const SSE_PROVIDER_ERROR_PARTIAL = `event: stage
data: {"stage":"retrieving","detail":null}

event: token
data: {"text":"Here's what operators say about pricing page redesigns: the"}

event: token
data: {"text":" biggest lever is usually reducing the number of decisions"}

event: error
data: {"code":"MODEL_TIMEOUT","message":"ollama did not respond within the configured timeout","retryable":true,"partial":true}

`;
