import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { activatePolicy, getPolicyDetail, updatePolicyMotors } from "../../src/api/client";
import { MotorCalibrationDTO, PolicyCode, PolicyDetail } from "../../src/api/types";
import { AppButton } from "../../src/components/AppButton";
import { MotorSlider } from "../../src/components/MotorSlider";
import { TopBar } from "../../src/components/TopBar";
import { useServer } from "../../src/context/ServerContext";
import { useAppTheme } from "../../src/theme/ThemeProvider";

export default function PolicyDetailScreen() {
  const { code } = useLocalSearchParams<{ code: PolicyCode }>();
  const { colors } = useAppTheme();
  const { baseUrl } = useServer();

  const [detail, setDetail] = useState<PolicyDetail | null>(null);
  const [motors, setMotors] = useState<MotorCalibrationDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    if (!baseUrl || !code) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getPolicyDetail(baseUrl, code);
      setDetail(data);
      setMotors(data.motors);
      setDirty(false);
    } catch (err: any) {
      setError(err?.message ?? "No se pudo cargar la política.");
    } finally {
      setLoading(false);
    }
  }, [baseUrl, code]);

  useEffect(() => {
    load();
  }, [load]);

  const handleMotorChange = (motorIndex: number, value: number) => {
    setMotors((prev) =>
      prev.map((m) => (m.motor_index === motorIndex ? { ...m, intensity_percent: value } : m)),
    );
    setDirty(true);
  };

  const handleSave = async () => {
    if (!code) return;
    setSaving(true);
    try {
      const updated = await updatePolicyMotors(
        baseUrl,
        code,
        motors.map((m) => ({
          motor_index: m.motor_index,
          intensity_percent: m.intensity_percent,
        })),
      );
      setDetail(updated);
      setMotors(updated.motors);
      setDirty(false);
    } catch (err: any) {
      Alert.alert("Error al guardar", err?.message ?? "Intentá de nuevo.");
    } finally {
      setSaving(false);
    }
  };

  const handleTestNow = async () => {
    if (!code) return;
    setTesting(true);
    try {
      await activatePolicy(baseUrl, code);
    } catch (err: any) {
      Alert.alert("No se pudo activar", err?.message ?? "Intentá de nuevo.");
    } finally {
      setTesting(false);
    }
  };

  return (
    <View style={[styles.screen, { backgroundColor: colors.background }]}>
      <TopBar showBack />

      {loading && !detail ? (
        <View style={styles.centered}>
          <ActivityIndicator color={colors.primary} size="large" />
        </View>
      ) : error && !detail ? (
        <View style={styles.centered}>
          <Text style={{ color: colors.danger, textAlign: "center", paddingHorizontal: 24 }}>
            {error}
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={[styles.badge, { backgroundColor: colors.badgeBg }]}>
            <Feather name="edit-3" size={11} color={colors.badgeText} />
            <Text style={[styles.badgeText, { color: colors.badgeText }]}>MODO EDICIÓN</Text>
          </View>

          <Text style={[styles.policyTitle, { color: colors.textPrimary }]}>
            {detail?.title}
          </Text>

          <Text style={[styles.description, { color: colors.textSecondary }]}>
            {detail?.description}
          </Text>

          <View style={styles.sectionHeaderRow}>
            <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
              Intensidad por Motor
            </Text>
            <Feather name="grid" size={16} color={colors.textSecondary} />
          </View>

          <View style={styles.grid}>
            {motors.map((motor) => (
              <MotorSlider
                key={motor.motor_index}
                label={motor.label}
                value={motor.intensity_percent}
                onChange={(value) => handleMotorChange(motor.motor_index, value)}
              />
            ))}
          </View>

          <AppButton
            label="Guardar Cambios del Patrón"
            onPress={handleSave}
            loading={saving}
            disabled={!dirty}
            icon={<Feather name="save" size={16} color="#fff" />}
          />

          <View style={{ height: 10 }} />

          <AppButton
            label="Probar patrón ahora"
            onPress={handleTestNow}
            variant="secondary"
            loading={testing}
            icon={<Feather name="play" size={16} color={colors.primary} />}
          />

          <View
            style={[
              styles.hintBox,
              { backgroundColor: colors.successSoft, borderColor: colors.success },
            ]}
          >
            <Feather name="info" size={14} color={colors.successText} />
            <Text style={[styles.hintText, { color: colors.successText }]}>
              Recordá que los cambios en la grilla se guardan directamente en
              el perfil de esta política, para el modo automático y manual.
            </Text>
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  centered: { flex: 1, alignItems: "center", justifyContent: "center" },
  content: { padding: 16, paddingBottom: 48 },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    marginBottom: 10,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  policyTitle: {
    fontSize: 24,
    fontWeight: "800",
    marginBottom: 8,
  },
  description: {
    fontSize: 13,
    fontStyle: "italic",
    lineHeight: 19,
    marginBottom: 20,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
  },
  hintBox: {
    flexDirection: "row",
    gap: 8,
    borderWidth: 1,
    borderRadius: 12,
    padding: 12,
    marginTop: 16,
  },
  hintText: {
    fontSize: 12,
    lineHeight: 17,
    flex: 1,
  },
});
