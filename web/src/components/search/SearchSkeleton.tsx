export function SearchSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <section>
        <div className="h-3 w-32 bg-muted-foreground/20 rounded-none mb-4" />
        <div className="space-y-2.5">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="flex items-start gap-3 sm:gap-[var(--grid-gap)] p-3 sm:p-4 rounded-none border border-border/10 bg-secondary/15"
            >
              <div className="w-14 sm:w-16 aspect-[4/3] rounded-none bg-muted-foreground/15 shrink-0" />
              <div className="flex-1 min-w-0 space-y-2">
                <div className="h-2.5 w-16 bg-muted-foreground/15 rounded-none" />
                <div className="h-3.5 w-5/6 bg-muted-foreground/15 rounded-none" />
                <div className="h-2.5 w-2/3 bg-muted-foreground/15 rounded-none" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
