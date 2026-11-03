let audioContext = null;
let audioUnlocked = false;

function getAudioContext() {
    if (typeof window === "undefined") return null;

    const AudioContextClass =
        window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) return null;

    if (!audioContext) {
        audioContext = new AudioContextClass();
    }

    return audioContext;
}

async function unlockAudio() {
    const context = getAudioContext();
    if (!context) return;

    try {
        if (context.state === "suspended") {
            await context.resume();
        }
        audioUnlocked = context.state === "running";
    } catch {
        audioUnlocked = false;
    }
}

export function armNotificationAudio() {
    if (typeof window === "undefined") return () => {};

    const unlock = () => {
        unlockAudio();
        window.removeEventListener("pointerdown", unlock);
        window.removeEventListener("keydown", unlock);
    };

    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });

    return () => {
        window.removeEventListener("pointerdown", unlock);
        window.removeEventListener("keydown", unlock);
    };
}

function scheduleTone(context, startAt, frequency, duration, volume) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();

    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(frequency, startAt);

    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(volume, startAt + 0.018);
    gain.gain.exponentialRampToValueAtTime(
        0.0001,
        startAt + duration
    );

    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(startAt);
    oscillator.stop(startAt + duration + 0.02);
}

export async function playNotificationChime() {
    const context = getAudioContext();
    if (!context) return false;

    try {
        if (!audioUnlocked || context.state === "suspended") {
            await unlockAudio();
        }

        if (context.state !== "running") {
            return false;
        }

        const now = context.currentTime + 0.01;
        scheduleTone(context, now, 740, 0.13, 0.09);
        scheduleTone(context, now + 0.14, 988, 0.18, 0.075);
        return true;
    } catch {
        return false;
    }
}
