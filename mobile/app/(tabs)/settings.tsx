import { Feather } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";

import { getStatus, stopMotors, updateStatus } from "../../src/api/client";
import { AppButton } from "../../src/components/AppButton";
import { TopBar } from "../../src/components/TopBar";
import { useServer } from "../../src/context/ServerContext";
import { useAppTheme } from "../../src/theme/ThemeProvider";

function SectionTitle({ children }: { children: string }) {
  const { colors } = useAppTheme();
  return (
    <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{children}</Text>
  );
}

export default function SettingsScreen() {
  const { colors, isDark, toggleDark } = useAppTheme();
  const { baseUrl, setBaseUrl, status, isReachable, refreshStatus } = useServer();

  const [urlDraft, setUrlDraft] = useState(baseUrl);
  const [testing, setTesting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [savingMode, setSavingMode] = useState(false);

  useEffect(() => setUrlDraft(baseUrl), [baseUrl]);

  const handleSaveUrl = async () => {
    await setBaseUrl(urlDraft.trim());
    Alert.alert("Guardado", "Dirección del servidor actualizada.");
    refreshStatus();
  };

  const handleTestConnection = async () => {
    setTesting(true);
    try {
      await getStatus(urlDraft.trim());
      Alert.alert("Conexión OK", "El backend respondió correctamente.");
    } catch (err: any) {
      Alert.alert("No se pudo conectar", err?.message ?? "Error desconocido");
    } finally {
      setTesting(false);
    }
  };

  const handleSetMode = async (mode: "auto" | "manual") => {
    setSavingMode(true);
    try {
      await updateStatus(baseUrl, { mode });
      refreshStatus();
    } catch (err: any) {
      Alert.alert("Error", err?.message ?? "No se pudo cambiar el modo.");
    } finally {
      setSavingMode(false);
    }
  };

  const handleStop = async () => {
    setStopping(true);
    try {
      await stopMotors(baseUrl);
    } catch (err: any) {
      Alert.alert("Error", err?.message ?? "No se pudo detener los motores.");
    } finally {
      setStopping(false);
    }
  };

  return (
    <View style={[styles.screen, { backgroundColor: colors.background }]}>
      <TopBar />
      <ScrollView contentContainerStyle={styles.content}>
        <SectionTitle>CONEXIÓN CON EL SERVIDOR</SectionTitle>
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.label, { color: colors.textSecondary }]}>
            Dirección del backend (IP:puerto de la PC con Django y el Arduino)
          </Text>
          <TextInput
            value={urlDraft}
            onChangeText={setUrlDraft}
            placeholder="http://192.168.0.10:8000"
            placeholderTextColor={colors.textSecondary}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            style={[
              styles.input,
              {
                color: colors.textPrimary,
                borderColor: colors.border,
                backgroundColor: colors.background,
              },
            ]}
          />
          <View style={styles.rowGap}>
            <View style={{ flex: 1 }}>
              <AppButton label="Guardar" onPress={handleSaveUrl} variant="primary" />
            </View>
            <View style={{ flex: 1 }}>
              <AppButton
                label="Probar conexión"
                onPress={handleTestConnection}
                variant="secondary"
                loading={testing}
              />
            </View>
          </View>

          <View style={styles.statusRow}>
            <View
              style={[
                styles.dot,
                { backgroundColor: isReachable ? colors.success : colors.danger },
              ]}
            />
            <Text style={[styles.statusText, { color: colors.textSecondary }]}>
              {isReachable
                ? `Servidor OK · Arduino ${status?.arduino_connected ? "conectado" : "desconectado"}`
                : "Sin respuesta del servidor"}
            </Text>
          </View>
        </View>

        <SectionTitle>MODO DE DECISIÓN</SectionTitle>
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.label, { color: colors.textSecondary }]}>
            Quién decide qué política aplicar según el pulso
          </Text>
          <View style={styles.segmentRow}>
            <SegmentButton
              label="Automático"
              active={status?.mode !== "manual"}
              onPress={() => handleSetMode("auto")}
              loading={savingMode}
            />
            <SegmentButton
              label="Manual"
              active={status?.mode === "manual"}
              onPress={() => handleSetMode("manual")}
              loading={savingMode}
            />
          </View>
          <Text style={[styles.hint, { color: colors.textSecondary }]}>
            En automático, el backend decide la política según el BPM. En
            manual, sólo se activa la política que elijas a mano desde la
            pestaña Patrones.
          </Text>
        </View>

        <SectionTitle>APARIENCIA</SectionTitle>
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <View style={styles.switchRow}>
            <View style={styles.switchLabelWrap}>
              <Feather name="moon" size={16} color={colors.textSecondary} />
              <Text style={[styles.switchLabel, { color: colors.textPrimary }]}>Modo oscuro</Text>
            </View>
            <Switch value={isDark} onValueChange={toggleDark} />
          </View>
        </View>

        <SectionTitle>ACCIONES</SectionTitle>
        <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <AppButton
            label="Detener motores ahora"
            onPress={handleStop}
            variant="danger"
            loading={stopping}
            icon={<Feather name="power" size={16} color="#fff" />}
          />
        </View>
      </ScrollView>
    </View>
  );
}

function SegmentButton({
  label,
  active,
  onPress,
  loading,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  loading: boolean;
}) {
  const { colors } = useAppTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={loading}
      style={[
        styles.segment,
        {
          backgroundColor: active ? colors.primary : "transparent",
          borderColor: colors.primary,
        },
      ]}
    >
      <Text style={{ color: active ? "#fff" : colors.primary, fontWeight: "700", fontSize: 13 }}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  sectionTitle: {
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 0.6,
    marginBottom: 8,
    marginTop: 4,
  },
  card: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    marginBottom: 20,
  },
  label: {
    fontSize: 12,
    marginBottom: 8,
  },
  input: {
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    marginBottom: 12,
  },
  rowGap: {
    flexDirection: "row",
    gap: 10,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 12,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    fontSize: 12,
  },
  segmentRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 10,
  },
  segment: {
    flex: 1,
    borderWidth: 1.5,
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: "center",
  },
  hint: {
    fontSize: 11,
    lineHeight: 15,
  },
  switchRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  switchLabelWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  switchLabel: {
    fontSize: 14,
  },
});
