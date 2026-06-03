import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";

/**
 * VoiceButton — the mic toggle. Pulses red while listening.
 * Props: supported, listening, onStart, onStop.
 */
export default function VoiceButton({ supported, listening, onStart, onStop }) {
    if (!supported) {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Icon name="mic_off" size={20} />
                <span>Voice not supported here — type the order below.</span>
            </div>
        );
    }

    return (
        <Button
            type="button"
            size="lg"
            variant={listening ? "destructive" : "default"}
            onClick={listening ? onStop : onStart}
            className={listening ? "animate-pulse" : ""}
        >
            <Icon name={listening ? "stop_circle" : "mic"} size={20} />
            {listening ? "Stop listening" : "Speak the order"}
        </Button>
    );
}
