import Slider from "@react-native-community/slider";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { useAppTheme } from "../theme/ThemeProvider";

interface Props {
  label: string;
  value: number; // 0..100
  onChange: (value: number) => void;
}

export function MotorSlider({ label, value, onChange }: Props) {
  const { colors } = useAppTheme();

  return (
    <View
      style={[styles.cell, { backgroundColor: colors.background, borderColor: colors.border }]}
    >
      <View style={styles.headerRow}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text>
        <Text style={[styles.value, { color: colors.textPrimary }]}>
          {Math.round(value)}%
        </Text>
      </View>
      <Slider
        style={styles.slider}
        minimumValue={0}
        maximumValue={100}
        step={1}
        value={value}
        minimumTrackTintColor={colors.primary}
        maximumTrackTintColor={colors.track}
        thumbTintColor={colors.sliderThumb}
        onValueChange={onChange}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  cell: {
    flexBasis: "48%",
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  label: {
    fontSize: 12,
    fontWeight: "700",
  },
  value: {
    fontSize: 13,
    fontWeight: "700",
  },
  slider: {
    width: "100%",
    height: 30,
  },
});
