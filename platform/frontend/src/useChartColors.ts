/** Resolve CSS custom properties to concrete colours for SVG charts.
 *
 * Recharts writes colours as SVG presentation *attributes* (`fill="..."`), and those
 * do not support `var()` — only CSS properties do. Passing `var(--series-1)` straight
 * through therefore produces correctly shaped but invisible bars.
 *
 * Reading the computed value keeps the stylesheet as the single source of truth while
 * handing Recharts something it can actually paint. The observer re-reads on a theme
 * change so dark mode picks up its own steps rather than reusing the light ones.
 */
import { useEffect, useState } from "react";

const TOKENS = [
  "--series-1",
  "--series-2",
  "--series-3",
  "--series-4",
  "--grid",
  "--border",
  "--surface-1",
  "--surface-2",
  "--text-primary",
  "--text-secondary",
  "--text-muted",
  "--good",
  "--warning",
  "--critical",
  "--accent",
] as const;

export type ChartColors = Record<(typeof TOKENS)[number], string>;

function read(): ChartColors {
  const styles = getComputedStyle(document.documentElement);
  const out = {} as ChartColors;
  for (const token of TOKENS) {
    out[token] = styles.getPropertyValue(token).trim() || "#888";
  }
  return out;
}

export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(() =>
    typeof window === "undefined" ? ({} as ChartColors) : read(),
  );

  useEffect(() => {
    const update = () => setColors(read());
    update();

    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);

    return () => {
      observer.disconnect();
      media.removeEventListener("change", update);
    };
  }, []);

  return colors;
}
