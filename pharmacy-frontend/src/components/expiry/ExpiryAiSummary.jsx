import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";

/**
 * The AI paragraph, and the report's own data caveats.
 *
 * This panel only renders text the backend produced. It holds no figures of its
 * own — the cards and the table above are the source of truth for every number, so
 * the two can never drift apart on screen.
 *
 * It loads after the table and fails softly: if the model is slow or down, the
 * pharmacist loses a paragraph, not the report.
 */
export default function ExpiryAiSummary({ explanation, explaining, error, notes }) {
    return (
        <Card className="gap-0 border-primary/20 bg-primary/[0.03] p-5">
            <div className="flex items-center gap-2">
                <span className="rounded-lg bg-primary/10 p-1.5 text-primary">
                    <Icon name="auto_awesome" size={18} />
                </span>
                <h2 className="text-sm font-semibold">AI summary</h2>

                {explanation && (
                    <span className="ml-auto text-[11px] text-muted-foreground">
                        confidence {Math.round(explanation.confidence * 100)}%
                    </span>
                )}
            </div>

            <div className="mt-3">
                {explaining && (
                    <div className="space-y-2" role="status" aria-live="polite">
                        <span className="sr-only">Writing the summary…</span>
                        <Skeleton className="h-3.5 w-full" />
                        <Skeleton className="h-3.5 w-[92%]" />
                        <Skeleton className="h-3.5 w-[70%]" />
                    </div>
                )}

                {!explaining && error && (
                    <p className="flex items-start gap-2 text-sm text-muted-foreground">
                        <Icon name="cloud_off" size={16} className="mt-0.5 shrink-0" />
                        <span>
                            {error} The figures above are unaffected — they are
                            calculated without the AI.
                        </span>
                    </p>
                )}

                {!explaining && !error && explanation && (
                    <p className="text-sm leading-relaxed whitespace-pre-line">
                        {explanation.answer}
                    </p>
                )}
            </div>

            {notes?.length > 0 && (
                <div className="mt-4 border-t border-border/60 pt-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        About this data
                    </p>
                    <ul className="mt-2 space-y-1">
                        {notes.map((note, i) => (
                            <li
                                key={i}
                                className="flex gap-2 text-xs text-muted-foreground"
                            >
                                <Icon name="info" size={14} className="mt-px shrink-0" />
                                <span>{note}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </Card>
    );
}
