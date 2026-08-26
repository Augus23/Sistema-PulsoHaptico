import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { PolicySummary } from "../api/types";
import { POLICY_UI } from "../theme/colors";
import { useAppTheme } from "../theme/ThemeProvider";

export function PolicyListItem({ policy }: { policy: PolicySummary }) {
  const { colors } = useAppTheme();
  const router = useRouter();
  const ui = POLICY_UI[policy.code] ?? POLICY_UI.reassure;

  return (
    <Pressable
      onPress={() => router.push(`/policy/${policy.code}`)}
      style={({ pressed }) => [
        styles.row,
        {
          backgroundColor: colors.card,
          borderColor: colors.border,
          opacity: pressed ? 0.85 : 1,
        },
      ]}
    >
      <View style={[styles.iconWrap, { backgroundColor: ui.iconBg }]}>
        <Feather name={ui.icon as any} size={20} color={ui.iconColor} />
      </View>

      <View style={styles.textCol}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>{policy.title}</Text>
        <Text
          style={[styles.description, { color: colors.textSecondary }]}
          numberOfLines={2}
        >
          {policy.description}
        </Text>
      </View>

      <Feather name="chevron-right" size={18} color={colors.textSecondary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    marginBottom: 12,
  },
  iconWrap: {
    width: 42,
    height: 42,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  textCol: {
    flex: 1,
  },
  title: {
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 2,
  },
  description: {
    fontSize: 12,
    lineHeight: 16,
  },
});
