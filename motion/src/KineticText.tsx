// Kinetic typography: words pop in at given timeline frames/positions.
// The look (font, weight, color, shadow) is set via props/data — defaults are neutral.
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";

// Default font: Inter (Latin + Cyrillic). Pass `fontFamily` to use any other loaded/system font.
const inter = loadFont("normal", { weights: ["400", "700", "900"], subsets: ["latin", "cyrillic"] });

export type Word = {
  text: string;
  in: number; // frame the word appears (timeline frame)
  out: number; // frame it disappears
  x: number; // left edge, fraction of width
  y: number; // baseline, fraction of height
  size: number; // px
  color?: string;
  shake?: boolean; // short jitter on entry
};

export type KineticProps = {
  words: Word[];
  color?: string;
  fontFamily?: string;
  fontWeight?: number;
  shadow?: boolean;
};

const WordView: React.FC<{ w: Word; p: Required<Omit<KineticProps, "words">> }> = ({ w, p }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  if (frame < w.in || frame >= w.out) return null;
  const t = frame - w.in;
  const enter = spring({ frame: t, fps, config: { damping: 11, stiffness: 220, mass: 0.6 } });
  const exit = interpolate(frame, [w.out - 6, w.out], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const scale = interpolate(enter, [0, 1], [0.55, 1]) * interpolate(exit, [0, 1], [0.8, 1]);
  const dy = interpolate(enter, [0, 1], [50, 0]);
  const opacity = Math.min(interpolate(t, [0, 3], [0, 1], { extrapolateRight: "clamp" }), exit);
  const jitter = w.shake && t < 14 ? Math.sin(t * 2.7) * (14 - t) * 0.9 : 0;
  return (
    <div
      style={{
        position: "absolute",
        left: w.x * width + jitter,
        top: w.y * height,
        transform: `translateY(calc(-100% + ${dy}px)) scale(${scale})`,
        transformOrigin: "left bottom",
        opacity,
        fontFamily: p.fontFamily,
        fontWeight: p.fontWeight,
        fontSize: w.size,
        lineHeight: 0.95,
        color: w.color ?? p.color,
        whiteSpace: "nowrap",
        textShadow: p.shadow ? "0 6px 24px rgba(0,0,0,0.45)" : undefined,
      }}
    >
      {w.text}
    </div>
  );
};

export const KineticText: React.FC<KineticProps> = ({
  words,
  color = "#FFFFFF",
  fontFamily = inter.fontFamily,
  fontWeight = 700,
  shadow = false,
}) => (
  <AbsoluteFill>
    {words.map((w, i) => (
      <WordView key={i} w={w} p={{ color, fontFamily, fontWeight, shadow }} />
    ))}
  </AbsoluteFill>
);
