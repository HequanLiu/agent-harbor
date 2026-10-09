import { Image } from "react-native";
/** Reuse the desktop app asset without redrawing the brand mark. */
export function BrandLogo({ size = 44 }: { size?: number }) {
  return (
    <Image
      accessibilityLabel="AgentHarbor 标志"
      accessibilityRole="image"
      source={require("../../assets/icon.png")}
      style={{ width: size, height: size, borderRadius: size * 0.25 }}
    />
  );
}
