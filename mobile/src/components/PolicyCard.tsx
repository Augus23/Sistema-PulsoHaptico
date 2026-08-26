import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PolicySummary } from "../api/types";
import { POLICY_UI } from "../theme/colors";
import { useAppTheme } from "../theme/ThemeProvider";

export function PolicyCard({ policy }: { policy: PolicySummary }) {
  const { colors } = useAppTheme();
  const router = useRouter();
  const ui = POLICY_UI[policy.code] ?? POLICY_UI.reassure;

  return (
    <Pressable
      onPress={() => router.push(`/policy/${policy.code}`)}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: colors.card,
          borderColor: colors.border,
          opacity: pressed ? 0.8 : 1,
        },
      ]}
    >
      <View style={[styles.iconWrap, { backgroundColor: ui.iconBg }]}>
        <Feather name={ui.icon as any} size={18} color={ui.iconColor} />
      </View>
      <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={2}>
        {policy.title}
      </Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]} numberOfLines={1}>
        {policy.subtitle}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexBasis: "48%",
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    marginBottom: 12,
  },
  iconWrap: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 10,
  },
  title: {
    fontSize: 13,
    fontWeight: "700",
    marginBottom: 2,
  },
  subtitle: {
    fontSize: 11,
  },
});
