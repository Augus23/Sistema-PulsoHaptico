import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAppTheme } from "../theme/ThemeProvider";

interface Props {
  showBack?: boolean;
  rightIcon?: keyof typeof Feather.glyphMap;
  onRightPress?: () => void;
}

export function TopBar({ showBack, rightIcon, onRightPress }: Props) {
  const { colors } = useAppTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View
      style={[
        styles.container,
        { backgroundColor: colors.headerBg, paddingTop: insets.top + 10 },
      ]}
    >
      <Pressable
        style={styles.sideSlot}
        onPress={() => (showBack ? router.back() : undefined)}
        hitSlop={12}
      >
        {showBack && <Feather name="chevron-left" size={22} color={colors.headerText} />}
      </Pressable>

      <View style={styles.titleWrap}>
        <Feather name="activity" size={16} color={colors.headerText} />
        <Text style={[styles.title, { color: colors.headerText }]}>Haptic Flow</Text>
      </View>

      <Pressable style={styles.sideSlot} onPress={onRightPress} hitSlop={12}>
        {rightIcon && <Feather name={rightIcon} size={20} color={colors.headerText} />}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    paddingBottom: 14,
    paddingHorizontal: 8,
  },
  sideSlot: {
    width: 40,
    alignItems: "center",
  },
  titleWrap: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  title: {
    fontSize: 16,
    fontWeight: "700",
  },
});
