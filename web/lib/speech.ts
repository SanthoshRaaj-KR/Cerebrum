/**
 * Reading the question aloud.
 *
 * Two voices, in order of preference:
 *
 * 1. The bridge's `/api/speak`, which is Deepgram Aura on the key already
 *    used for dictation. It sounds like a person.
 * 2. The browser's own `speechSynthesis`. Worse, and on some machines
 *    considerably worse, but it is always there and it starts instantly.
 *
 * The fallback is not a nicety. The first voice is a network round trip
 * in front of a question someone is sitting waiting to hear, and the
 * failure modes are ordinary ones - no key, out of quota, offline, slow.
 * A silent interview is the outcome actually worth avoiding, so anything
 * that goes wrong falls through to the browser rather than surfacing an
 * error the candidate has to deal with mid-question.
 *
 * Everything here is one-at-a-time by construction. Starting a new
 * utterance stops the previous one, because two questions talking over
 * each other is worse than either of them.
 */

const BRIDGE = process.env.NEXT_PUBLIC_BRIDGE ?? "http://127.0.0.1:7332";

/** Audio the browser has already been given, keyed by the exact text.
 * Pressing replay on a question should not pay for the same bytes twice,
 * and it makes a re-read instant. Object URLs are revoked when the map is
 * cleared at the end of a session. */
const cache = new Map<string, string>();

let current: HTMLAudioElement | null = null;

export type SpeechEnd = () => void;

/** Stops whatever is talking. Safe to call when nothing is. */
export function stop() {
  if (current) {
    current.pause();
    current.src = "";
    current = null;
  }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

/** Frees the cached audio. Called when an interview ends. */
export function reset() {
  stop();
  for (const url of cache.values()) URL.revokeObjectURL(url);
  cache.clear();
}

/**
 * Picks the least robotic voice available locally.
 *
 * Chrome's default pick is frequently the worst one installed, so this
 * prefers the named natural voices that ship with Windows and macOS and
 * only then falls back to whatever is first. Getting this wrong is the
 * difference between "a person asked me a question" and "my computer read
 * me a form".
 */
function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const english = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const pool = english.length ? english : voices;
  const preferred = [
    "natural", "neural", "google us english", "samantha", "aria", "jenny",
    "libby", "sonia", "ava", "zira",
  ];
  for (const want of preferred) {
    const hit = pool.find((v) => v.name.toLowerCase().includes(want));
    if (hit) return hit;
  }
  return pool[0] ?? null;
}

function browserSpeak(text: string, onEnd?: SpeechEnd): boolean {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    onEnd?.();
    return false;
  }
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voice = pickVoice();
    if (voice) u.voice = voice;
    // A shade under default. Interview questions carry a clause or two of
    // setup before the actual ask, and the default rate runs through that
    // faster than someone can follow while also thinking about an answer.
    u.rate = 0.95;
    u.pitch = 1;
    u.onend = () => onEnd?.();
    u.onerror = () => onEnd?.();
    window.speechSynthesis.speak(u);
    return true;
  } catch {
    onEnd?.();
    return false;
  }
}

/**
 * Says one question out loud.
 *
 * Resolves when the audio has been handed off, not when it finishes -
 * pass `onEnd` for that. Never rejects: a failure to speak is not an
 * error the candidate should have to deal with in the middle of being
 * asked something.
 *
 * @param serverVoice whether to try the bridge first. False goes straight
 *        to the browser, which is what the console does when it already
 *        knows the bridge has no speech key.
 */
export async function speak(
  text: string,
  { serverVoice = true, onEnd }: { serverVoice?: boolean; onEnd?: SpeechEnd } = {},
): Promise<void> {
  stop();
  const clean = text.trim();
  if (!clean) return;

  if (serverVoice) {
    try {
      let url = cache.get(clean);
      if (!url) {
        const r = await fetch(`${BRIDGE}/api/speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: clean }),
        });
        if (!r.ok) throw new Error(String(r.status));
        const blob = await r.blob();
        if (!blob.size) throw new Error("empty");
        url = URL.createObjectURL(blob);
        cache.set(clean, url);
      }
      const audio = new Audio(url);
      audio.onended = () => {
        current = null;
        onEnd?.();
      };
      // A decode failure this late still has somewhere to go.
      audio.onerror = () => {
        current = null;
        browserSpeak(clean, onEnd);
      };
      current = audio;
      // play() rejects when the browser has not seen a user gesture yet.
      // Starting an interview is a click, so in practice it has - but a
      // rejection here must still land somewhere rather than throwing
      // into a render.
      await audio.play();
      return;
    } catch {
      // fall through to the browser voice
    }
  }

  browserSpeak(clean, onEnd);
}

/** Whether anything can speak at all, before trying. Used to decide
 * whether the toggle is worth showing. */
export function supported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/* -- the preference ---------------------------------------------------------
 *
 * Whether questions are read aloud, remembered between sessions. Stored
 * rather than defaulted every time because this is a preference about a
 * room, not about a screen: someone practising on a train wants it off,
 * and will want it off tomorrow too.
 *
 * It lives here as a tiny external store rather than as React state for
 * the same reason the theme does. The server renders this screen too and
 * cannot know the stored value, so reading it into state inside an effect
 * would render once with the wrong icon and then correct itself - a
 * cascading render, and a visible flicker on the glyph.
 * useSyncExternalStore exists for exactly this shape.
 *
 * Default on. The point of the feature is to hear the question, and a
 * feature that has to be discovered before it does anything is one most
 * people never meet.
 */
const VOICE_KEY = "cerebrum-voice";
const listeners = new Set<() => void>();

export function subscribeVoice(onChange: () => void) {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function voicePref(): boolean {
  try {
    return localStorage.getItem(VOICE_KEY) !== "off";
  } catch {
    // Storage throws outright in some contexts rather than returning
    // null, and a muted interview is not worth a blank page.
    return true;
  }
}

/** What the server renders. Matches the default so the common case
 * hydrates without a flicker. */
export function voicePrefServer(): boolean {
  return true;
}

export function setVoicePref(on: boolean) {
  try {
    localStorage.setItem(VOICE_KEY, on ? "on" : "off");
  } catch {
    // Not being able to remember the choice is no reason to refuse it.
  }
  for (const fn of listeners) fn();
}
