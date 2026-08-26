export const lightColors = {
  background: "#F3F5FA",
  card: "#FFFFFF",
  headerBg: "#12203A",
  headerText: "#FFFFFF",
  textPrimary: "#111827",
  textSecondary: "#6B7280",
  border: "#E5E7EB",
  primary: "#2F6FEB",
  primarySoft: "#E7EFFE",
  success: "#16A34A",
  successSoft: "#E7F8ED",
  successText: "#166534",
  danger: "#DC2626",
  track: "#E5E7EB",
  sliderThumb: "#2F6FEB",
  badgeBg: "#EEF2FF",
  badgeText: "#4338CA",
};

export const darkColors = {
  background: "#0B1220",
  card: "#141C2E",
  headerBg: "#0B1220",
  headerText: "#F3F5FA",
  textPrimary: "#F3F5FA",
  textSecondary: "#9AA5B8",
  border: "#26314A",
  primary: "#5B8DF6",
  primarySoft: "#1D2A47",
  success: "#34D399",
  successSoft: "#123024",
  successText: "#6EE7B7",
  danger: "#F87171",
  track: "#26314A",
  sliderThumb: "#5B8DF6",
  badgeBg: "#1D2A47",
  badgeText: "#9DB2FF",
};

export type ThemeColors = typeof lightColors;

// Un icono + color por política, para las tarjetas de Inicio/Patrones.
// Los nombres de icono son de la familia Feather (@expo/vector-icons).
export const POLICY_UI: Record<
  string,
  { icon: string; iconBg: string; iconColor: string }
> = {
  awareness: { icon: "zap", iconBg: "#DCEBFF", iconColor: "#2563EB" },
  reassure: { icon: "heart", iconBg: "#DFF7E6", iconColor: "#16A34A" },
  breath: { icon: "wind", iconBg: "#EDE4FF", iconColor: "#7C3AED" },
  calm_down: { icon: "arrow-down", iconBg: "#E5E7EB", iconColor: "#374151" },
};
