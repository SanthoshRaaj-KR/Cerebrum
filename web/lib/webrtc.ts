import { BRIDGE_URL } from "./api";

export type MicStatus = "idle" | "connecting" | "listening" | "failed" | "ended";

export type MicHandlers = {
  onStatusChange: (status: MicStatus) => void;
  onError: (message: string) => void;
  /** A finalised chunk of speech, to be appended to the answer box. */
  onTranscript: (text: string) => void;
  /** The in-progress guess at the current sentence. Deepgram revises this
   * as you speak, so it replaces rather than appends - it exists so the
   * UI can show something is happening before you pause. */
  onInterim: (text: string) => void;
};

// Pipecat's RTVI message shapes (pipecat.processors.frameworks.rtvi.models),
// sent as JSON over the data channel we open below. The backend pipeline is
// dictation only - transport -> VAD -> Deepgram STT, no LLM and no audio
// coming back down this connection - so the only message that matters here
// is the user's own transcription. The interviewer's voice is a separate
// thing entirely: a plain request to /api/speak, see lib/speech.ts.
type RtviMessage = {
  label: string;
  type: string;
  data?: { text?: string; final?: boolean };
};

/**
 * Microphone dictation over WebRTC against the bridge's /api/offer endpoint
 * (pipecat's SmallWebRTCTransport on the other end). Speech goes up, text
 * comes back on the data channel, and it lands in the answer box - the
 * interview itself stays a request/response over the REST API.
 *
 * Non-trickle ICE: we wait for gathering to finish before sending the
 * offer, which is simpler than a separate candidate-patching endpoint and
 * is plenty fast for a same-machine connection - there's no NAT to
 * traverse.
 */
export class MicSession {
  private pc: RTCPeerConnection | null = null;
  private micStream: MediaStream | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private readonly handlers: MicHandlers;

  constructor(handlers: MicHandlers) {
    this.handlers = handlers;
  }

  async start(): Promise<void> {
    this.handlers.onStatusChange("connecting");

    // getUserMedia does not reject while a permission prompt is sitting
    // unanswered - it simply never settles. Without a deadline the UI stays
    // on "connecting" forever and looks broken, which is indistinguishable
    // from a real fault. Time it out and say what to actually do.
    let micStream: MediaStream;
    try {
      const stream = await withTimeout(
        navigator.mediaDevices.getUserMedia({ audio: true }),
        MIC_PERMISSION_TIMEOUT_MS
      );
      if (stream === TIMED_OUT) {
        this.handlers.onStatusChange("failed");
        this.handlers.onError(
          "Still waiting on microphone permission. Look for your browser's " +
            "mic prompt and choose Allow, then try again - or just type your answer."
        );
        return;
      }
      micStream = stream;
    } catch {
      this.handlers.onStatusChange("failed");
      this.handlers.onError(
        "Microphone access was denied or unavailable. Allow mic access and try again."
      );
      return;
    }
    this.micStream = micStream;

    const pc = new RTCPeerConnection();
    this.pc = pc;

    micStream.getTracks().forEach((track) => pc.addTrack(track, micStream));

    // Pipecat's SmallWebRTCConnection only ever listens for a data channel
    // WE open (aiortc's "datachannel" event fires for a channel created by
    // the remote peer) - it never creates one itself. Must exist before
    // createOffer() so the SDP even has an application m-line.
    this.dataChannel = pc.createDataChannel("rtvi");
    this.dataChannel.onmessage = (event) => this.handleDataChannelMessage(event.data);

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "connected") {
        this.handlers.onStatusChange("listening");
      } else if (pc.connectionState === "failed") {
        this.handlers.onStatusChange("failed");
        this.handlers.onError(
          "Mic connection failed. If the backend is in Docker this is expected - " +
            "WebRTC media can't reach the container. Type your answer instead."
        );
      } else if (pc.connectionState === "closed") {
        this.handlers.onStatusChange("ended");
      }
    };

    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await waitForIceGatheringComplete(pc);

      const res = await fetch(`${BRIDGE_URL}/api/offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sdp: pc.localDescription!.sdp,
          type: pc.localDescription!.type,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        throw new Error(body.detail || `offer failed (${res.status})`);
      }

      await pc.setRemoteDescription({ type: body.type, sdp: body.sdp });
    } catch (err) {
      this.handlers.onStatusChange("failed");
      this.handlers.onError(err instanceof Error ? err.message : "could not connect");
      this.stop();
    }
  }

  stop(): void {
    this.dataChannel?.close();
    this.dataChannel = null;
    this.pc?.close();
    this.pc = null;
    this.micStream?.getTracks().forEach((track) => track.stop());
    this.micStream = null;
    this.handlers.onStatusChange("ended");
  }

  private handleDataChannelMessage(raw: string): void {
    if (raw.startsWith("ping")) return; // pipecat's own keepalive, not JSON
    let msg: RtviMessage;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    if (msg.label !== "rtvi-ai" || !msg.data?.text) return;
    if (msg.type !== "user-transcription") return;
    // Deepgram emits several interim guesses per sentence and then exactly
    // one final. Only the final is committed, or the answer box would fill
    // up with half-sentences.
    if (msg.data.final) {
      this.handlers.onInterim("");
      this.handlers.onTranscript(msg.data.text);
    } else {
      this.handlers.onInterim(msg.data.text);
    }
  }
}

/** How long to wait for ICE gathering before sending the offer anyway. */
const ICE_GATHERING_TIMEOUT_MS = 2000;

/** How long to sit on an unanswered microphone permission prompt. */
const MIC_PERMISSION_TIMEOUT_MS = 12000;

const TIMED_OUT = Symbol("timed-out");

/** Resolves to TIMED_OUT rather than hanging if `promise` never settles. */
async function withTimeout<T>(
  promise: Promise<T>,
  ms: number
): Promise<T | typeof TIMED_OUT> {
  let timer: ReturnType<typeof setTimeout>;
  const deadline = new Promise<typeof TIMED_OUT>((resolve) => {
    timer = setTimeout(() => resolve(TIMED_OUT), ms);
  });
  try {
    return await Promise.race([promise, deadline]);
  } finally {
    clearTimeout(timer!);
  }
}

/**
 * Resolves when ICE gathering finishes, or after a short deadline.
 *
 * The deadline matters: gathering can stall indefinitely (a browser waiting
 * on an unreachable STUN server, a headless or locked-down environment with
 * no usable interfaces), and without it the offer is never sent at all - the
 * UI just sits on "connecting" forever with nothing in the server log to
 * explain it. Host candidates are gathered first and are the only ones that
 * matter for a same-machine connection, so proceeding with a partial list
 * costs nothing here.
 */
async function waitForIceGatheringComplete(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return;
  await new Promise<void>((resolve) => {
    const done = () => {
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    function check() {
      if (pc.iceGatheringState === "complete") done();
    }
    const timer = setTimeout(done, ICE_GATHERING_TIMEOUT_MS);
    pc.addEventListener("icegatheringstatechange", check);
  });
}
