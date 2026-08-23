import { BRIDGE_URL } from "./api";

export type VoiceStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "failed"
  | "ended";

export type TranscriptSpeaker = "interviewer" | "you";

export type VoiceSessionHandlers = {
  onStatusChange: (status: VoiceStatus) => void;
  onError: (message: string) => void;
  onTranscript: (speaker: TranscriptSpeaker, text: string) => void;
};

// Pipecat's RTVI message shapes (pipecat.processors.frameworks.rtvi.models),
// sent as JSON over the data channel we open below. Only the two transcript
// message types are handled here - RTVI carries a lot more (speaking
// state, metrics, function calls) that this UI has no use for yet.
type RtviMessage = {
  label: string;
  type: string;
  data?: { text?: string; final?: boolean };
};

/**
 * One WebRTC voice session against the bridge's /api/offer endpoint
 * (pipecat's SmallWebRTCTransport on the other end). Non-trickle ICE: we
 * wait for gathering to finish before sending the offer, which is simpler
 * than a separate candidate-patching endpoint and is plenty fast for a
 * same-machine, local-only connection - there's no NAT to traverse.
 */
export class VoiceSession {
  private pc: RTCPeerConnection | null = null;
  private micStream: MediaStream | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private readonly audioEl: HTMLAudioElement;
  private readonly handlers: VoiceSessionHandlers;

  constructor(audioEl: HTMLAudioElement, handlers: VoiceSessionHandlers) {
    this.audioEl = audioEl;
    this.handlers = handlers;
  }

  async start(role: string, mode: string): Promise<void> {
    this.handlers.onStatusChange("connecting");

    let micStream: MediaStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
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

    pc.ontrack = (event) => {
      this.audioEl.srcObject = event.streams[0];
    };

    // Pipecat's SmallWebRTCConnection only ever listens for a data channel
    // WE open (aiortc's "datachannel" event fires for a channel created by
    // the remote peer) - it never creates one itself. Must exist before
    // createOffer() so the SDP even has an application m-line.
    this.dataChannel = pc.createDataChannel("rtvi");
    this.dataChannel.onmessage = (event) => this.handleDataChannelMessage(event.data);

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "connected") {
        this.handlers.onStatusChange("connected");
      } else if (pc.connectionState === "failed") {
        this.handlers.onStatusChange("failed");
        this.handlers.onError("Voice connection failed.");
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
          request_data: { role, mode },
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

  /** Toggles the mic track's enabled state (not the connection) and
   * returns whether it's now muted. Muting this way keeps the WebRTC
   * connection and audio track alive - it just stops sending real audio -
   * which is far cheaper than tearing down and renegotiating the session. */
  toggleMute(): boolean {
    const track = this.micStream?.getAudioTracks()[0];
    if (!track) return false;
    track.enabled = !track.enabled;
    return !track.enabled;
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

    if (msg.type === "bot-transcription") {
      this.handlers.onTranscript("interviewer", msg.data.text);
    } else if (msg.type === "user-transcription" && msg.data.final) {
      this.handlers.onTranscript("you", msg.data.text);
    }
  }
}

async function waitForIceGatheringComplete(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return;
  await new Promise<void>((resolve) => {
    function check() {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    }
    pc.addEventListener("icegatheringstatechange", check);
  });
}
