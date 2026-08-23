import { BRIDGE_URL } from "./api";

export type VoiceStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "failed"
  | "ended";

export type VoiceSessionHandlers = {
  onStatusChange: (status: VoiceStatus) => void;
  onError: (message: string) => void;
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
    this.pc?.close();
    this.pc = null;
    this.micStream?.getTracks().forEach((track) => track.stop());
    this.micStream = null;
    this.handlers.onStatusChange("ended");
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
