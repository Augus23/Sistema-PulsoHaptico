export type PolicyCode = "reassure" | "awareness" | "breath" | "calm_down";

export interface PolicySummary {
  code: PolicyCode;
  title: string;
  subtitle: string;
  description: string;
}

export interface MotorCalibrationDTO {
  motor_index: number;
  label: string;
  intensity_percent: number;
}

export interface PolicyDetail extends PolicySummary {
  motors: MotorCalibrationDTO[];
}

export type SystemMode = "auto" | "manual";

export interface SystemStatus {
  global_intensity_percent: number;
  mode: SystemMode;
  active_policy: PolicyCode | null;
  last_bpm: number | null;
  last_smooth_bpm: number | null;
  last_baseline_bpm: number | null;
  last_signal_ok: boolean;
  last_phase: string;
  arduino_connected: boolean;
}
