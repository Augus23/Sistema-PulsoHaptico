import Slider from "@react-native-community/slider";
import React, { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { useAppTheme } from "../theme/ThemeProvider";

interface Props {
  value: number; // 0..100
  onChangeComplete: (value: number) => void;
  disabled?: boolean;
}

export function GlobalIntensitySlider({ value, onChangeComplete, disabled }: Props) {
  const { colors } = useAppTheme();
  const [localValue, setLocalValue] = useState(value);

  // Si el valor llega de afuera (ej. primer fetch), sincronizamos el slider.
  React.useEffect(() => {
    setLocalValue(value);
  }, [value]);

  return (
    <View
      style={[styles.container, { backgroundColor: colors.card, borderColor: colors.border }]}
    >
      <View style={styles.headerRow}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          INTENSIDAD GLOBAL
        </Text>
        <Text style={[styles.value, { color: colors.textPrimary }]}>
          {Math.round(localValue)}%
        </Text>
      </View>

      <Slider
        style={styles.slider}
        minimumValue={0}
        maximumValue={100}
        step={1}
        value={value}
        disabled={disabled}
        minimumTrackTintColor={colors.primary}
        maximumTrackTintColor={colors.track}
        thumbTintColor={colors.sliderThumb}
        onValueChange={setLocalValue}
        onSlidingComplete={onChangeComplete}
      />

      <View style={styles.captionRow}>
        <Text style={[styles.captionEdge, { color: colors.textSecondary }]}>Silencioso</Text>
        <Text style={[styles.captionEdge, { color: colors.textSecondary }]}>Intenso</Text>
      </View>
      <Text style={[styles.hint, { color: colors.textSecondary }]}>
        Afecta a los 6 motores de las 4 políticas por igual.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  label: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  value: {
    fontSize: 18,
    fontWeight: "700",
  },
  slider: {
    width: "100%",
    height: 36,
    marginTop: 4,
  },
  captionRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: -6,
  },
  captionEdge: {
    fontSize: 11,
  },
  hint: {
    fontSize: 11,
    marginTop: 8,
  },
});
