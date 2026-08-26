import React from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { useAppTheme } from "../theme/ThemeProvider";

interface Props {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  loading?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
}

export function AppButton({
  label,
  onPress,
  variant = "primary",
  loading,
  disabled,
  icon,
}: Props) {
  const { colors } = useAppTheme();

  const backgroundColor =
    variant === "primary"
      ? colors.primary
      : variant === "danger"
      ? colors.danger
      : "transparent";

  const textColor = variant === "secondary" ? colors.primary : "#FFFFFF";
  const borderColor = variant === "secondary" ? colors.primary : backgroundColor;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor,
          borderColor,
          opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
        },
      ]}
    >
      {loading ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <View style={styles.content}>
          {icon}
          <Text style={[styles.label, { color: textColor }]}>{label}</Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    borderWidth: 1.5,
    borderRadius: 14,
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  label: {
    fontSize: 14,
    fontWeight: "700",
  },
});
