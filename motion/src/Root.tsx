import { Composition } from "remotion";
import { KineticText, KineticProps } from "./KineticText";
import example from "./data/example.json";

// Кадры в данных — кадры таймлайна DaVinci. Ставь fps композиции равным fps таймлайна (например 59.94),
// иначе Resolve проигрывает оверлей в реальном времени и текст уплывает от монтажа.
export const Root: React.FC = () => (
  <Composition
    id="KineticText"
    component={KineticText}
    durationInFrames={900}
    fps={59.94}
    width={1920}
    height={1080}
    defaultProps={example as KineticProps}
  />
);
