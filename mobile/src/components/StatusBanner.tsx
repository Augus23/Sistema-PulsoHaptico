import { Feather } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { useServer } from "../context/ServerContext";
import { useAppTheme } from "../theme/ThemeProvider";

export function StatusBanner() {
  const { colors } = useAppTheme();
  const { status, isReachable } = useServer();

  const connected = isReachable && !!status?.arduino_connected;

  let bpmLabel = "--";
  if (status?.last_phase === "baseline") {
    bpmLabel = "Calculando línea base…";
  } else if (status?.last_smooth_bpm != null) {
    bpmLabel = `${status.last_smooth_bpm} BPM`;
  }

  return (
    <View
      style={[
        styles.container,
        { backgroundColor: colors.card, borderColor: colors.border },
      ]}
    >
      <View style={styles.row}>
        <View
          style={[
            styles.dot,
            { backgroundColor: connected ? colors.success : colors.danger },
          ]}
        />
        <Text style={[styles.title, { color: colors.textPrimary }]}>
          {connected ? "Arduino conectado" : "Sin conexión"}
        </Text>
        <View style={[styles.badge, { backgroundColor: colors.badgeBg }]}>
          <Text style={[styles.badgeText, { color: colors.badgeText }]}>
            {status?.mode === "manual" ? "Manual" : "Automático"}
          </Text>
        </View>
      </View>

      <View style={styles.row}>
        <Feather name="activity" size={16} color={colors.textSecondary} />
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
          {bpmLabel}
          {status?.active_policy ? `  ·  política activa: ${status.active_policy}` : ""}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    gap: 8,
    marginBottom: 16,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  title: {
    fontSize: 15,
    fontWeight: "600",
    flex: 1,
  },
  subtitle: {
    fontSize: 13,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: "700",
  },
});
