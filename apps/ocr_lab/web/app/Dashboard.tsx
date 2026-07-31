"use client";

import { useEffect, useMemo, useState } from "react";
import {
  pendingReviewCases,
  resumePendingReview,
} from "./review-queue.mjs";

const SHOW_HELDOUT = import.meta.env.VITE_SHOW_HELDOUT === "true";

type Sample = {
  sampleId: string;
  documentId: string;
  documentType: string;
  sourceFormat: string;
  variant: string;
  pages: number;
  ocrSuccess: boolean;
  avgConfidence: number | null;
  durationMs: number;
  cer: number | null;
  wer: number | null;
  exactMatchRate: number | null;
  fieldPresenceRate: number | null;
  evaluatedFieldCount: number;
  mainErrors: string[];
  baseline: {
    ocrSuccess: boolean | null;
    avgConfidence: number | null;
    durationMs: number | null;
    cer: number | null;
    wer: number | null;
    exactMatchRate: number | null;
    fieldPresenceRate: number | null;
  };
};

type Phase = {
  number: number;
  name: string;
  status: string;
  summary: string;
  result: string;
};

type DashboardData = {
  phases: Phase[];
  nextSteps: Array<{ order: number; title: string; description: string }>;
  processing: {
    engine: string;
    ocrVersion: string;
    language: string;
    device: string;
    models?: { textDetection?: string; textRecognition?: string };
  };
  summary: {
    nativeJsonCount: number;
    ocrSuccessCount: number;
    groundTruthDocumentCount: number;
    matchedGroundTruthDocumentCount: number;
    evaluatedSampleCount: number;
    evaluatedFieldInstanceCount: number;
    cer: number;
    wer: number;
    exactMatchRate: number;
    fieldPresenceRate: number;
    durationMs: { total: number; mean: number; p50: number; p95: number };
  };
  baselineSummary: {
    nativeJsonCount: number;
    ocrSuccessCount: number;
    cer: number;
    wer: number;
    exactMatchRate: number;
    fieldPresenceRate: number;
    durationMs: { total: number; mean: number; p50: number; p95: number };
  };
  samples: Sample[];
};

type HeldoutMetric = {
  documentCount: number;
  classificationAccuracy: number;
  evaluatedFieldCount: number;
  fieldExactMatchCount: number;
  fieldExactMatchRate: number;
  fieldCompleteness: number;
  acceptedFieldRate: number;
  cer: number;
  wer: number;
  der: number;
  expectedTableRowCount: number;
  exactTableRowCount: number;
  tableExactRowRate: number;
  expectedTableCellCount: number;
  exactTableCellCount: number;
  tableExactCellRate: number;
  tableCompleteness: number;
};

type HeldoutDocument = {
  documentId: string;
  documentFamily: string;
  sourceFormat: string;
  sizeBytes: number;
  previewAvailable: boolean;
  sourceAvailable: boolean;
};

type ReplayAudit = {
  evaluationKind: string;
  documentCount: number;
  visualDocumentsReOcred?: number;
  nativeDocumentsReparsed?: number;
  visualDocumentCount?: number;
  nativeDocumentCount?: number;
  ocrPipeline?: string;
  eligibleForPromotion: false;
  baseline: {
    overall: HeldoutMetric;
    sensitiveFieldFalseAcceptanceCount: number;
  };
  latest: {
    overall: HeldoutMetric;
    sensitiveFieldFalseAcceptanceCount: number;
  };
  delta: Record<string, number>;
  decision: {
    status: string;
    production: string;
    reason: string;
  };
};

type HeldoutSummary = {
  schemaVersion: string;
  datasetId: string;
  datasetDigest: string;
  containsRealPII: true;
  localAccessAuthorized: true;
  publicReleaseAuthorized: boolean;
  predictionsVisibleDuringGroundTruthReview: false;
  recognitionPolicyDigest: string;
  parserVersion: string;
  metricSpecVersion: string;
  evaluatedAt: string;
  evaluationRunCount: number;
  thresholdRetuned: false;
  predictionsWereHidden: true;
  documentCount: number;
  countsByFamily: Record<string, number>;
  overall: HeldoutMetric;
  byFamily: Record<string, HeldoutMetric>;
  sensitiveFieldFalseAcceptanceCount: number;
  decision: {
    controlledPilot: string;
    production: string;
  };
  latestReplay?: ReplayAudit | null;
  latestLiveV5Replay?: ReplayAudit | null;
  documents: HeldoutDocument[];
};

type LocalEvidenceDetail = {
  schemaVersion: string;
  documentId: string;
  documentFamily: string;
  documentType?: string;
  schemaRef: string;
  containsRealPII: true;
  localOnly: true;
  groundTruth: Record<string, unknown>;
  prediction: Record<string, unknown>;
  sealedPrediction?: Record<string, unknown>;
  lockedReplayPrediction?: Record<string, unknown> | null;
  liveV5Prediction?: Record<string, unknown> | null;
  predictionLabel?: string;
  predictionNotice?: string;
  predictionProvenance?: {
    defaultSource: "live_v5" | "locked_replay" | "sealed";
    sealed: {
      sealedAt?: string;
      parserVersion?: string;
      recognitionPolicyDigest?: string;
      evaluationKind: string;
    };
    lockedReplay?: {
      createdAt?: string;
      parserVersion?: string;
      recognitionPolicyDigest?: string;
      evaluationKind?: string;
      promotionEligible?: boolean;
    } | null;
    liveV5?: {
      createdAt?: string;
      parserVersion?: string;
      recognitionPolicyDigest?: string;
      evaluationKind?: string;
      promotionEligible?: boolean;
      ocrPipeline?: string;
    } | null;
  };
};

type Detail = {
  sampleId: string;
  documentId: string;
  sourceRelativePath: string;
  variant: string;
  recognizedTexts: string[];
  recognitionScores: number[];
  hasVisualization: boolean;
};

type UserPage = {
  pageIndex: number;
  recognizedTexts: string[];
  recognizedText: string;
  recognitionScores: number[];
  avgConfidence: number | null;
  durationMs: number;
  visualizationAvailable: boolean;
};

type Phase9Line = {
  sourceIndex: number;
  outputIndex: number;
  rawText: string;
  correctedText: string;
  confidence: number | null;
  correctionApplied: boolean;
  correctionMethod: string | null;
  warning: string | null;
};

type IdentityField = {
  value: string | null;
  asciiValue?: string | null;
  confidence: number | null;
  status: "accepted" | "needs_review" | "not_found";
  asciiStatus?: "verified_base_text" | "needs_review" | "not_found";
  errorSignals?: string[];
  selectionMode?: "exact_consensus" | "base_text_consensus" | "single_candidate";
  validation: {
    valid: boolean;
    rule: string;
    confidenceThreshold: number;
    labelMatchScore: number;
  };
  evidence: {
    engine?: string;
    pageIndex: number;
    lineIndices?: number[];
    bbox: number[][] | null;
    texts?: string[];
    candidates?: Array<Record<string, unknown>>;
  } | null;
};

type UnifiedBusinessField = {
  value: unknown;
  normalizedValue?: unknown;
  dataType?: string;
  confidence: number | null;
  status: "accepted" | "needs_review" | "not_found";
  sensitive?: boolean;
  validation?: {
    valid: boolean;
    method?: string;
  };
  evidence: Record<string, unknown> | null;
};

type UnifiedIdpResult = {
  version: string;
  status: "READY" | "NEEDS_REVIEW";
  ingestion: {
    sourceFormat: string;
    mode: "NATIVE" | "SCAN" | "HYBRID";
    adapter: string;
    pageCount: number;
  };
  classification: {
    documentType: string;
    documentSubtype?: string;
    documentFamily?: string;
    workflowDocumentType?: string;
    schemaRef?: string;
    confidence: number;
    status: "accepted" | "needs_review";
    evidence: string[];
  };
  extraction: {
    fields: Record<string, UnifiedBusinessField>;
    tables: Array<{
      tableIndex?: number;
      tableType?: string;
      sourceKind?: string;
      rows: Array<{
        rowIndex: number;
        values?: unknown;
        status: "accepted" | "needs_review";
      }>;
      summary: {
        rowCount: number;
        acceptedRowCount: number;
        columnCount: number;
      };
    }>;
    summary: {
      expectedFieldCount: number;
      presentFieldCount: number;
      acceptedFieldCount: number;
      needsReviewFieldCount: number;
      notFoundFieldCount: number;
      documentCompleteness: number;
      acceptedCoverage: number;
    };
  };
  durationMs: number;
  review?: {
    reviewStatus: "USER_REVIEWED";
    reviewedAt: string;
    correctedFieldCount: number;
  };
};

type UserResult = {
  sessionId: string;
  createdAt: string;
  containsRealPII: boolean;
  retention: string;
  source: {
    originalFileName: string;
    format: string;
    sizeBytes: number;
    pageCount: number;
  };
  processing: {
    profile: string;
    ocrVersion: string;
    inferenceDurationMs: number;
    totalDurationMs: number;
  };
  document: {
    documentType: string;
    ocrSuccess: boolean;
    recognizedText: string;
    rawRecognizedText?: string;
    correctedText?: string;
    recognizedTextLineCount: number;
    avgConfidence: number | null;
    extractedCandidates: Record<string, string[]>;
    pages: UserPage[];
  };
  phase9?: {
    version: string;
    documentRoute: {
      type: string;
      confidence: number;
      evidence: string[];
    };
    selectedVariant: "phase8_raw" | "phase9_routed";
    pages: Array<{
      pageIndex: number;
      readingOrderStrategy: string;
      lines: Phase9Line[];
      rawText: string;
      correctedText: string;
    }>;
    qualityGate: {
      status: "PASS" | "REVIEW" | "FAIL";
      requiresHumanReview: boolean;
      lowConfidenceLineCount: number;
      lowConfidenceRatio: number;
      warnings: string[];
      validation: Record<string, number>;
    };
  };
  phase11?: {
    version: string;
    status: "PASS" | "NEEDS_REVIEW" | "NOT_APPLICABLE";
    orientation: {
      strategy: string;
      pages: Array<{
        pageIndex: number;
        selectedRotationDegrees: number;
        selectionScore: number;
        identityLikely: boolean;
      }>;
    };
    canonicalization?: Array<{
      pageIndex: number;
      perspectiveCorrected: boolean;
      canonicalSize: number[];
      selectedVariant: string;
    }>;
    pages?: Array<{
      pageIndex: number;
      selectedVariant: string;
      readingOrderStrategy: string;
      lines: Phase9Line[];
      rawText: string;
    }>;
    identityCard: {
      fields: Record<string, IdentityField>;
      summary: {
        expectedFieldCount: number;
        presentFieldCount: number;
        acceptedFieldCount: number;
        needsReviewFieldCount: number;
        notFoundFieldCount: number;
        documentCompleteness: number;
        acceptedRate: number;
        readyForAutomaticUse: boolean;
      };
    } | null;
    durationMs: number;
  };
  phase11_3?: {
    version: string;
    status: "COMPLETE";
    strategy: string;
    targetFields: string[];
    configurationNames: string[];
    replacementDecisions: Record<
      string,
      {
        replaced: boolean;
        reason: string;
        candidateStatus: string;
        consensusCount: number;
      }
    >;
  };
  phase11_4?: {
    version: string;
    status: "COMPLETE";
    strategy: string;
    targetedFields: string[];
    consensusGatedFields: string[];
    decisions: Record<
      string,
      {
        previousStatus: string;
        finalStatus: string;
        downgraded?: boolean;
        replaced?: boolean;
        manualReviewRequired?: boolean;
      }
    >;
    durationMs: number;
  };
  phase11_5?: {
    version: string;
    status: "COMPLETE";
    mode: "SHADOW_REVIEW_ONLY";
    strategy: string;
    recognizers: string[];
    cropProfiles: string[];
    durationMs: number;
  };
  phase14_8?: {
    version: string;
    status: string;
    policy?: {
      primaryProfile?: string;
      verifierProfile?: string;
      paddleSelectionEligible?: boolean;
    };
    summary: {
      pageCount: number;
      lineCount: number;
      verifiedLineCount: number;
      needsReviewLineCount: number;
      verifiedRate?: number;
    };
    durationMs: number;
    download?: string;
  };
  phase12?: UnifiedIdpResult;
  phase15?: UnifiedIdpResult;
};

type SupportedTemplate = {
  templateId: string;
  documentType: string;
  version: string;
  supportedFileTypes: string[];
  requiredFields: string[];
  optionalFields: string[];
};

type TemplateProcessingResult = {
  status: "SUCCESS";
  documentType: string;
  templateId: string;
  templateVersion: string;
  detection: {
    matchedAnchors: string[];
    detectionConfidence: number;
  };
  data: Record<string, unknown> & {
    documentId: string;
    recommendedAction: string;
  };
  quality: {
    missingFields: string[];
    validationErrors: string[];
    confidence: number;
    recommendedAction: string;
  };
  camundaVariables: Record<string, unknown>;
};

type TemplateSessionSummary = {
  documentId: string;
  createdAt: string;
  originalFileName: string;
  documentType: "LEAVE_REQUEST" | "OVERTIME_REQUEST";
  templateId: string;
  templateVersion: string;
  status: string;
  recommendedAction: string | null;
  confidence: number | null;
};

type UserSessionSummary = {
  sessionId: string;
  createdAt: string;
  originalFileName: string;
  format: string;
  pageCount: number;
  ocrSuccess: boolean;
  recognizedTextLineCount: number;
  avgConfidence: number | null;
  totalDurationMs: number;
  documentType?: string;
  qualityGate?: string | null;
  processingProfile?: string | null;
  ocrVersion?: string | null;
  phase11Version?: string | null;
  phase14_8Status?: string | null;
  reviewed?: boolean;
  phase15Reviewed?: boolean;
};

type Phase10Review = {
  reviewed: boolean;
  reviewStatus: "DRAFT" | "NEEDS_RECONFIRMATION" | "USER_REVIEWED";
  draftPages: Array<{ pageIndex: number; text: string }>;
  groundTruth: {
    reviewedAt: string;
    verificationAssertions?: {
      comparedWithImage: boolean;
      allTextChecked: boolean;
      acceptUnchangedDraft: boolean;
      unchangedFromDraft: boolean;
    };
    pages: Array<{ pageIndex: number; text: string }>;
    identityFields?: Record<string, string>;
  } | null;
  identityFieldDraft: Record<string, string>;
  challenger: {
    available: boolean;
    engine?: string;
    version?: string;
    avgConfidence?: number | null;
    durationMs?: number;
    draftPages?: Array<{ pageIndex: number; text: string }>;
    identityCard?: {
      fields: Record<string, IdentityField>;
    } | null;
  };
  hybrid: {
    available: boolean;
    phase?: string;
    status?: string;
    policy?: {
      detector?: string;
      primaryRecognizer?: string;
      verifier?: string;
      autoAcceptRule?: string;
      disagreementRule?: string;
      productionPromotionAllowed?: boolean;
    };
    runtime?: {
      durationMs?: number;
      easyocrVersion?: string;
      vietocrVersion?: string;
    };
    summary?: {
      cropCount?: number;
      acceptedLineCount?: number;
      needsReviewLineCount?: number;
      acceptanceRate?: number;
    };
    pages?: Array<{
      pageIndex: number;
      recognizedText: string;
      lineCount: number;
      acceptedLineCount: number;
      needsReviewLineCount: number;
    }>;
  };
  evaluation: {
    aggregate: Partial<Record<
      "phase8Raw" | "phase9Selected" | "phase9Corrected" | "easyocrChallenger",
      { cer: number; wer: number; exactMatch: boolean }
    >>;
    fieldEvaluation?: {
      groundTruthFieldCount: number;
      variants: Partial<Record<
        "phase9Before" | "phase11After" | "easyocrChallenger",
        {
          fieldExactMatch: number;
          documentCompleteness: number;
          exactMatchCount: number;
          presentFieldCount: number;
          groundTruthFieldCount: number;
        }
      >>;
    };
  } | null;
  businessJson: {
    verificationStatus: string;
    fields: Record<string, Array<{ value: string; verified: boolean }>>;
  } | null;
};

type Phase14Benchmark = {
  alignmentStatus: string;
  documentCount: number;
  lineCount: number;
  reviewedLineCount: number;
  evaluationDocumentCount?: number;
  evaluationLineCount?: number;
  datasetContentDigest: string;
  profiles: Record<
    string,
    {
      exactMatchRate: number;
      cer: number;
      wer: number;
      diacriticErrorRate: number;
      p95DurationMs: number;
    }
  >;
  selection: {
    bestEasyProfile: string;
    bestCropProfile: string;
    bestEasyCropProfile?: string;
    vietocrCropProfile?: string;
    recommendedPrimary?: string;
    paddleVerifiedCount?: number;
    paddleVerifiedPrecision?: number;
    promotionDecision: string;
    productionDecision?: string;
    verifierPolicy?: string;
    recommendedPrimaryAgreementCount?: number;
    recommendedPrimaryAgreementCoverage?: number;
    recommendedPrimaryAgreementPrecision?: number;
    fallbackRecognizer?: string;
    autoAcceptVerifier?: string | null;
  };
  recommendedConfiguration?: {
    detector?: string;
    primaryRecognizer?: string;
    cropProfile?: string;
    secondaryVerifier?: string;
    autoAcceptRule?: string;
    reviewRule?: string;
  };
  controlledPilot?: {
    sessionCount: number;
    failedSessionCount: number;
    summary: {
      cropCount: number;
      acceptedLineCount: number;
      needsReviewLineCount: number;
      acceptanceRate: number;
      totalDurationMs: number;
    };
    decision: {
      pilotStatus: string;
      productionStatus: string;
    };
  };
  phase14_3?: {
    lineCount: number;
    baselineFailureCount: number;
    profiles: Record<
      string,
      {
        exactMatchRate: number;
        cer: number;
        wer: number;
        diacriticErrorRate: number;
        p95DurationMs: number;
      }
    >;
    selected: {
      selectedPrimaryProfile: string;
      selectedCropProfile: string;
      fallbackRecognizer: string;
      fallbackMode: string;
      autoAcceptVerifier: string | null;
      productionDecision: string;
    };
    errorAnalysis: {
      categoryCounts: Record<string, number>;
      oracleRecoveryUpperBound: {
        otherVietocrCrop: number;
        paddleRecognizer: number;
        bestEasyRecognizer: number;
      };
    };
    verification: {
      anyVietCropAgreesWithPaddle: {
        count: number;
        coverage: number;
        precision: number;
      };
      anyVietCropAgreesWithBestEasy: {
        count: number;
        coverage: number;
        precision: number;
      };
    };
  };
  groundTruthExpansion?: {
    status: string;
    documentCount: number;
    lineCount: number;
    reviewedLineCount: number;
    pendingReviewLineCount: number;
    cropProfile: string;
    queueDigest: string;
  };
  secondRecognizer?: {
    config: string;
    weightAvailable: boolean;
    weightBytes: number;
    benchmarkReady: boolean;
    blockedByPendingReviewCount: number;
  };
  blindedPrecompute?: {
    status: string;
    lineCount: number;
    predictionsHiddenDuringReview: boolean;
    queueDigestMatches: boolean;
    privateArtifactSha256: string;
    runtime: Record<
      string,
      {
        lineCount: number;
        emptyPredictionCount: number;
        meanDurationMs: number;
        p95DurationMs: number;
      }
    >;
    totalDurationMs: number;
  };
  secondRecognizerBenchmark?: {
    groundTruthStatus: string;
    lineCount: number;
    documentCount: number;
    predictionSource: string;
    profiles: Record<
      string,
      {
        exactMatchRate: number;
        cer: number;
        wer: number;
        diacriticErrorRate: number;
        meanDurationMs: number;
        p95DurationMs: number;
      }
    >;
    decision: {
      selectedPrimary: string;
      challengerDecision: string;
      productionDecision: string;
    };
  };
  lineReviews: Record<
    string,
    {
      groundTruth: string;
      reviewedAt: string;
      comparedWithCrop: boolean;
      allTextChecked: boolean;
    }
  >;
  cases: Array<{
    caseId: string;
    groundTruth: string;
    crops: Record<string, { path: string; sha256: string }>;
    predictions: Record<
      string,
      { text: string; confidence: number; durationMs: number }
    >;
  }>;
};

const API_BASE = "http://127.0.0.1:8765";
const TEMPLATE_RESULT_META_FIELDS = new Set([
  "documentId",
  "documentType",
  "templateId",
  "templateVersion",
  "missingFields",
  "validationErrors",
  "confidence",
  "recommendedAction",
  "sourceFile",
]);

function normalizePhase10Review(payload: Phase10Review): Phase10Review {
  return {
    ...payload,
    reviewStatus:
      payload.reviewStatus ??
      (payload.reviewed
        ? "USER_REVIEWED"
        : payload.groundTruth
          ? "NEEDS_RECONFIRMATION"
          : "DRAFT"),
    draftPages: payload.draftPages ?? [],
    groundTruth: payload.groundTruth ?? null,
    identityFieldDraft: payload.identityFieldDraft ?? {},
    challenger: payload.challenger ?? { available: false },
    hybrid: payload.hybrid ?? { available: false },
    evaluation: payload.evaluation ?? null,
    businessJson: payload.businessJson ?? null,
  };
}

const typeLabels: Record<string, string> = {
  EMPLOYMENT_CONTRACT: "Hợp đồng",
  PROBATION_AGREEMENT: "Hợp đồng thử việc",
  CV: "CV",
  EMPLOYEE_INFORMATION_FORM: "Phiếu nhân viên",
  EMPLOYEE_INFO_UPDATE: "Phiếu cập nhật nhân sự",
  EMPLOYEE_MASTER_LIST: "Danh sách nhân sự",
  ONBOARDING_CHECKLIST: "Checklist tiếp nhận",
  TRAINING_ATTENDANCE: "Danh sách đào tạo",
  HR_DECISION: "Quyết định",
  TIMESHEET: "Bảng chấm công",
  LEAVE_REQUEST: "Đơn nghỉ phép",
  OVERTIME_REQUEST: "Phiếu làm thêm giờ",
  BUSINESS_TRIP_REQUEST: "Đề nghị công tác",
  EQUIPMENT_REQUEST: "Đề nghị cấp thiết bị",
  DEGREE: "Bằng cấp",
  DEGREE_CERTIFICATE: "Bằng cấp / chứng chỉ",
  GENERIC_PDF: "PDF tổng quát",
  GENERIC_DOCUMENT: "Tài liệu tổng quát",
  IDENTITY_DOCUMENT: "Giấy tờ định danh",
  PUBLIC_OCR: "Public OCR",
};

const familyLabels: Record<string, string> = {
  CV: "CV & hồ sơ ứng viên",
  ADMINISTRATIVE_REQUEST: "Đơn & biểu mẫu hành chính",
  CONTRACT_DECISION: "Hợp đồng & quyết định nhân sự",
  DEGREE_CERTIFICATE: "Bằng cấp & chứng chỉ",
  EMPLOYEE_FORM_TABLE: "Phiếu nhân viên & bảng biểu",
  IDENTITY_DOCUMENT: "Giấy tờ định danh",
  OTHER_HR_DOCUMENT: "Tài liệu HCNS cần phân loại",
};

const businessFieldLabels: Record<string, string> = {
  fullName: "Họ và tên",
  headline: "Vị trí / tiêu đề nghề nghiệp",
  email: "Email",
  phoneNumber: "Số điện thoại",
  phone: "Số điện thoại",
  address: "Địa chỉ",
  education: "Học vấn",
  experience: "Kinh nghiệm",
  skills: "Kỹ năng",
  documentTitle: "Tên biểu mẫu",
  requestNumber: "Số phiếu",
  employeeName: "Tên nhân viên",
  employeeId: "Mã nhân viên",
  department: "Phòng ban",
  jobTitle: "Chức danh",
  reason: "Lý do / mục đích",
  startDate: "Ngày bắt đầu",
  endDate: "Ngày kết thúc",
  documentNumber: "Số văn bản",
  action: "Nội dung quyết định",
  salary: "Mức lương",
  effectiveDate: "Ngày hiệu lực",
  recipientName: "Người được cấp",
  credentialType: "Loại văn bằng",
  credentialId: "Số hiệu văn bằng",
  issuingOrganization: "Đơn vị cấp",
  fieldOfStudy: "Ngành đào tạo",
  degreeLevel: "Trình độ",
  classification: "Xếp loại",
  issueDate: "Ngày cấp",
  formNumber: "Mã biểu mẫu",
  dateOfBirth: "Ngày sinh",
  gender: "Giới tính",
  organization: "Đơn vị",
  joinDate: "Ngày vào làm",
  requestDate: "Ngày làm đơn",
  leaveDays: "Số ngày nghỉ",
  expectedReturnDate: "Ngày dự kiến trở lại",
  handoverTo: "Người nhận bàn giao",
  handoverDepartment: "Bộ phận nhận bàn giao",
  handoverTasks: "Công việc bàn giao",
  approverName: "Người phê duyệt",
  laborContractNumber: "Số hợp đồng lao động",
  laborContractDate: "Ngày ký hợp đồng",
  standardWorkSchedule: "Lịch làm việc tiêu chuẩn",
  overtimeHoursPerDay: "Số giờ tăng ca mỗi ngày",
  overtimeStartTime: "Giờ bắt đầu tăng ca",
  overtimeEndTime: "Giờ kết thúc tăng ca",
  totalOvertimeHours: "Tổng số giờ tăng ca",
  workContent: "Nội dung công việc",
};

const identityFieldLabels: Record<string, string> = {
  identityNumber: "Số CCCD",
  fullName: "Họ và tên",
  dateOfBirth: "Ngày sinh",
  sex: "Giới tính",
  nationality: "Quốc tịch",
  placeOfOrigin: "Quê quán",
  placeOfResidence: "Nơi thường trú",
  dateOfExpiry: "Có giá trị đến",
};

const phase17Steps = [
  {
    order: 1,
    title: "Lập error set từ held-out thật",
    description:
      "Phân nhóm lỗi detection, crop, mất dấu, thay ký tự, reading order, classifier và parser theo từng family/field.",
  },
  {
    order: 2,
    title: "Cải thiện trên development-only",
    description:
      "Huấn luyện/fine-tune recognizer hoặc crop policy trên dữ liệu development riêng; tuyệt đối không chỉnh theo 18 tài liệu đã tiêu thụ.",
  },
  {
    order: 3,
    title: "Gated fallback không phá dòng đúng",
    description:
      "Chỉ cho phép switch khi có verifier agreement và regression chứng minh zero correct-line loss; còn lại needs_review.",
  },
  {
    order: 4,
    title: "Held-out v2 độc lập",
    description:
      "Khóa policy/model mới rồi prediction ẩn → Ground Truth → evaluate-once trên tập mới để quyết định promote theo family.",
  },
];

function pct(value: number | null, digits = 1) {
  return value === null ? "Chưa có" : `${(value * 100).toFixed(digits)}%`;
}

function decimal(value: number | null) {
  return value === null ? "Chưa có" : value.toFixed(4);
}

function duration(ms: number) {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function signedPoints(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  const points = value * 100;
  return `${points >= 0 ? "+" : ""}${points.toFixed(2)} điểm %`;
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function evidenceValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Không có";
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  const record = objectRecord(value);
  if ("normalizedValue" in record && record.normalizedValue != null) {
    return String(record.normalizedValue);
  }
  if ("value" in record) return evidenceValue(record.value);
  return JSON.stringify(value);
}

function evidenceBaseText(value: unknown): string {
  return evidenceValue(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[Đ]/g, "D")
    .replace(/[đ]/g, "d")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
}

function evidenceErrorClass(
  groundTruth: unknown,
  prediction: unknown,
): string {
  const expected = evidenceValue(groundTruth).trim();
  const actual = evidenceValue(prediction).trim();
  if (!actual || actual === "Không có") return "not_found";
  if (expected.normalize("NFC") === actual.normalize("NFC")) return "exact";
  const expectedBase = evidenceBaseText(expected);
  const actualBase = evidenceBaseText(actual);
  if (expectedBase === actualBase) return "diacritics_only";
  const expectedCompact = expectedBase.replace(/\s+/g, "");
  const actualCompact = actualBase.replace(/\s+/g, "");
  if (expectedCompact === actualCompact) return "line_merge_or_split";
  let cursor = 0;
  for (const character of expectedCompact) {
    if (character === actualCompact[cursor]) cursor += 1;
  }
  if (
    cursor === actualCompact.length &&
    actualCompact.length < expectedCompact.length
  ) {
    return "character_omission";
  }
  if (
    actualCompact.length < expectedCompact.length * 0.55 ||
    actualCompact.length > expectedCompact.length * 1.8
  ) {
    return "region_mismatch";
  }
  return "character_substitution";
}

function EvidenceInspector({
  detail,
  loading,
  error,
  view,
  onViewChange,
  downloads = [],
}: {
  detail: LocalEvidenceDetail | null;
  loading: boolean;
  error: string;
  view: "fields" | "json";
  onViewChange: (view: "fields" | "json") => void;
  downloads?: Array<{ label: string; href: string }>;
}) {
  const hasReplayComparison = Boolean(
    (detail?.liveV5Prediction || detail?.lockedReplayPrediction) &&
      detail?.sealedPrediction,
  );
  const [predictionSource, setPredictionSource] =
    useState<"live_v5" | "locked_replay" | "sealed">("live_v5");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset selection for a new evidence document.
    setPredictionSource(
      detail?.predictionProvenance?.defaultSource ?? "sealed",
    );
  }, [detail?.documentId, detail?.predictionProvenance?.defaultSource]);
  const selectedPrediction = (() => {
    if (predictionSource === "sealed") {
      return detail?.sealedPrediction ?? detail?.prediction;
    }
    if (predictionSource === "locked_replay") {
      return detail?.lockedReplayPrediction ?? detail?.prediction;
    }
    return detail?.liveV5Prediction ?? detail?.prediction;
  })();
  const groundTruthFields = objectRecord(detail?.groundTruth.fields);
  const predictionFields = objectRecord(selectedPrediction?.fields);
  const fieldNames = Array.from(
    new Set([
      ...Object.keys(groundTruthFields),
      ...Object.keys(predictionFields),
    ]),
  );

  return (
    <aside className="evidence-inspector" aria-live="polite">
      <header>
        <div>
          <span>SCHEMA / JSON</span>
          <strong>{detail?.documentType ?? detail?.documentFamily ?? "Đang tải"}</strong>
        </div>
        <small>{detail?.schemaRef ?? "Dữ liệu chỉ đọc trên localhost"}</small>
      </header>
      {hasReplayComparison ? (
        <div className="evidence-prediction-source">
          <span>NGUỒN PREDICTION</span>
          {detail?.liveV5Prediction ? (
            <button
              className={predictionSource === "live_v5" ? "active" : ""}
              onClick={() => setPredictionSource("live_v5")}
            >
              Live v5 mới nhất · parser 2.0
            </button>
          ) : null}
          {detail?.lockedReplayPrediction ? (
            <button
              className={predictionSource === "locked_replay" ? "active" : ""}
              onClick={() => setPredictionSource("locked_replay")}
            >
              Policy khóa v4 · parser 2.0
            </button>
          ) : null}
          <button
            className={predictionSource === "sealed" ? "active" : ""}
            onClick={() => setPredictionSource("sealed")}
          >
            Sealed · parser 1.0
          </button>
          <small>
            Live v5 và replay parser chạy sau khi Ground Truth đã mở — chỉ dùng
            audit, không dùng promotion.
          </small>
        </div>
      ) : detail?.predictionLabel ? (
        <div className="evidence-prediction-source evidence-prediction-source-single">
          <span>NGUỒN PREDICTION</span>
          <strong>{detail.predictionLabel}</strong>
          {detail.predictionNotice ? (
            <small>{detail.predictionNotice}</small>
          ) : null}
        </div>
      ) : null}
      <div className="evidence-inspector-tabs" role="tablist">
        <button
          className={view === "fields" ? "active" : ""}
          onClick={() => onViewChange("fields")}
          role="tab"
          aria-selected={view === "fields"}
        >
          Trường schema
        </button>
        <button
          className={view === "json" ? "active" : ""}
          onClick={() => onViewChange("json")}
          role="tab"
          aria-selected={view === "json"}
        >
          JSON
        </button>
      </div>
      {loading ? (
        <div className="evidence-inspector-state">Đang tải dữ liệu đối chiếu...</div>
      ) : error ? (
        <div className="evidence-inspector-state error">{error}</div>
      ) : !detail ? (
        <div className="evidence-inspector-state">Chọn một tài liệu để xem dữ liệu.</div>
      ) : view === "fields" ? (
        <div className="evidence-field-list">
          <div className="evidence-field-heading">
            <span>Trường</span>
            <span>Ground Truth</span>
            <span>Prediction tiếng Việt</span>
            <span>Prediction không dấu</span>
            <span>Error class</span>
          </div>
          {fieldNames.length ? (
            fieldNames.map((name) => {
              const prediction = objectRecord(predictionFields[name]);
              const evidence = objectRecord(prediction.evidence);
              const candidates = Array.isArray(evidence.candidates)
                ? evidence.candidates
                : [];
              const errorSignals = Array.isArray(prediction.errorSignals)
                ? prediction.errorSignals.map(String)
                : [];
              const computedErrorClass = evidenceErrorClass(
                groundTruthFields[name],
                predictionFields[name],
              );
              const displayedErrors = Array.from(
                new Set([computedErrorClass, ...errorSignals]),
              );
              return (
                <div className="evidence-field-row" key={name}>
                  <strong>{name}</strong>
                  <span>{evidenceValue(groundTruthFields[name])}</span>
                  <span>
                    {evidenceValue(predictionFields[name])}
                    {prediction.status ? (
                      <small data-status={String(prediction.status)}>
                        {String(prediction.status)}
                      </small>
                    ) : null}
                  </span>
                  <span>
                    {prediction.asciiValue
                      ? String(prediction.asciiValue)
                      : "—"}
                    {prediction.asciiStatus ? (
                      <small className="evidence-ascii-value">
                        {String(prediction.asciiStatus)}
                      </small>
                    ) : null}
                  </span>
                  <span>
                    {displayedErrors.join(", ")}
                    {candidates.length ? (
                      <details className="evidence-candidates">
                        <summary>
                          Crop &amp; {candidates.length} candidates
                        </summary>
                        <a
                          href={`${API_BASE}/user/phase11-5-crop?id=${encodeURIComponent(
                            detail.documentId,
                          )}&field=${encodeURIComponent(
                            name,
                          )}&variant=balanced_padding`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Mở crop đối chiếu
                        </a>
                        <pre>{JSON.stringify(candidates, null, 2)}</pre>
                      </details>
                    ) : null}
                  </span>
                </div>
              );
            })
          ) : (
            <div className="evidence-inspector-state">
              Schema hiện chưa có trường scalar cho tài liệu này.
            </div>
          )}
          {"tables" in detail.groundTruth ? (
            <div className="evidence-table-note">
              Tài liệu có Ground Truth dạng bảng. Xem tab JSON để đối chiếu toàn bộ
              hàng và ô.
            </div>
          ) : null}
        </div>
      ) : (
        <pre className="evidence-json">
          {JSON.stringify(
            {
              documentId: detail.documentId,
              schemaRef: detail.schemaRef,
              predictionSource,
              groundTruth: detail.groundTruth,
              prediction: selectedPrediction,
              provenance: detail.predictionProvenance,
            },
            null,
            2,
          )}
        </pre>
      )}
      {downloads.length ? (
        <footer>
          {downloads.map((download) => (
            <a href={download.href} key={download.href}>
              {download.label}
            </a>
          ))}
        </footer>
      ) : null}
    </aside>
  );
}

function TemplateEvidenceInspector({
  result,
  loading,
  error,
  view,
  onViewChange,
}: {
  result: TemplateProcessingResult | null;
  loading: boolean;
  error: string;
  view: "fields" | "json";
  onViewChange: (view: "fields" | "json") => void;
}) {
  const fields = result
    ? Object.entries(result.data).filter(
        ([name]) => !TEMPLATE_RESULT_META_FIELDS.has(name),
      )
    : [];

  return (
    <aside className="evidence-inspector" aria-live="polite">
      <header>
        <div>
          <span>SCHEMA / JSON</span>
          <strong>{result?.documentType ?? "TEMPLATE-FIRST"}</strong>
        </div>
        <small>
          {result
            ? `${result.templateId} / phiên bản ${result.templateVersion}`
            : "Kết quả biểu mẫu chỉ đọc trên localhost"}
        </small>
      </header>
      {result ? (
        <div className="evidence-prediction-source evidence-prediction-source-single">
          <span>NGUỒN DỮ LIỆU</span>
          <strong>Native DOCX / Template-first parser</strong>
          <small>
            {result.quality.recommendedAction} / confidence{" "}
            {pct(result.quality.confidence)}
          </small>
        </div>
      ) : null}
      <div className="evidence-inspector-tabs" role="tablist">
        <button
          className={view === "fields" ? "active" : ""}
          onClick={() => onViewChange("fields")}
          role="tab"
          aria-selected={view === "fields"}
        >
          Trường schema
        </button>
        <button
          className={view === "json" ? "active" : ""}
          onClick={() => onViewChange("json")}
          role="tab"
          aria-selected={view === "json"}
        >
          JSON
        </button>
      </div>
      {loading ? (
        <div className="evidence-inspector-state">Đang tải kết quả Template-first...</div>
      ) : error ? (
        <div className="evidence-inspector-state error">{error}</div>
      ) : !result ? (
        <div className="evidence-inspector-state">
          Chọn đơn nghỉ phép hoặc tăng ca để xem metadata và JSON.
        </div>
      ) : view === "fields" ? (
        <div className="evidence-field-list">
          <div className="template-evidence-field-heading">
            <span>Trường schema</span>
            <span>Giá trị trích xuất</span>
            <span>Trạng thái</span>
          </div>
          {fields.map(([name, value]) => {
            const isMissing = result.quality.missingFields.includes(name);
            return (
              <div className="template-evidence-field-row" key={name}>
                <strong>{name}</strong>
                <span>{formatTemplateValue(value)}</span>
                <small data-status={isMissing ? "not_found" : "accepted"}>
                  {isMissing ? "missing" : "extracted"}
                </small>
              </div>
            );
          })}
        </div>
      ) : (
        <pre className="evidence-json">{JSON.stringify(result, null, 2)}</pre>
      )}
    </aside>
  );
}

function phase11Label(result: UserResult) {
  return result.phase11_5
    ? "11.5"
    : result.phase11_4
      ? "11.4"
      : result.phase11_3
        ? "11.3"
        : "11.2";
}

function formatTemplateValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Không có trong tài liệu";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map(String).join(", ") : "Không có";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function TemplateResultPanel({
  result,
  filename,
  deleteArmed,
  onDelete,
}: {
  result: TemplateProcessingResult;
  filename: string;
  deleteArmed: boolean;
  onDelete: () => void;
}) {
  const fields = Object.entries(result.data).filter(
    ([name]) => !TEMPLATE_RESULT_META_FIELDS.has(name),
  );
  const isAutoContinue =
    result.quality.recommendedAction === "AUTO_CONTINUE";

  return (
    <div
      className="user-result-panel template-result-panel"
      data-testid="template-result-panel"
    >
      <div className="user-result-head">
        <div>
          <p className="eyebrow">TEMPLATE-FIRST RESULT</p>
          <h3>{filename}</h3>
          <span>
            {result.templateId} / phiên bản {result.templateVersion}
          </span>
        </div>
        <span
          className={`status-pill ${isAutoContinue ? "success" : "review"}`}
        >
          {result.quality.recommendedAction}
        </span>
      </div>

      <div className="template-summary-grid">
        <div>
          <span>LOẠI TÀI LIỆU</span>
          <strong>{result.documentType}</strong>
        </div>
        <div>
          <span>TRẠNG THÁI</span>
          <strong>{result.status}</strong>
        </div>
        <div>
          <span>CONFIDENCE</span>
          <strong>{pct(result.quality.confidence)}</strong>
        </div>
        <div>
          <span>ANCHOR MATCH</span>
          <strong>{pct(result.detection.detectionConfidence)}</strong>
        </div>
      </div>

      {(result.quality.missingFields.length > 0 ||
        result.quality.validationErrors.length > 0) && (
        <div className="template-quality-notices">
          {result.quality.missingFields.length > 0 && (
            <div>
              <span>TRƯỜNG KHÔNG XUẤT HIỆN</span>
              <p>{result.quality.missingFields.join(", ")}</p>
            </div>
          )}
          {result.quality.validationErrors.length > 0 && (
            <div className="error">
              <span>VALIDATION ERRORS</span>
              <p>{result.quality.validationErrors.join(", ")}</p>
            </div>
          )}
        </div>
      )}

      <section className="template-fields" aria-label="Kết quả trích xuất Template-first">
        <div className="phase15-fields-head">
          <div>
            <span>STRUCTURED TEMPLATE FIELDS</span>
            <h4>Thông tin trích xuất từ biểu mẫu chuẩn</h4>
          </div>
          <small>Giá trị trống được giữ null, không tự suy luận</small>
        </div>
        <div className="template-field-grid">
          {fields.map(([name, value]) => (
            <article
              className={`template-field ${
                value === null || value === "" ? "missing" : ""
              }`}
              key={name}
            >
              <span>{businessFieldLabels[name] ?? name}</span>
              <strong>{formatTemplateValue(value)}</strong>
              <small>{name}</small>
            </article>
          ))}
        </div>
      </section>

      <details className="template-json">
        <summary>Xem JSON đầy đủ</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>

      <div className="result-actions template-result-actions">
        <button
          className={deleteArmed ? "armed" : ""}
          onClick={onDelete}
          type="button"
        >
          {deleteArmed
            ? "Bấm lần nữa để xóa session local"
            : "Xóa kết quả local"}
        </button>
      </div>
    </div>
  );
}

export default function Dashboard({ data }: { data: DashboardData }) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("ALL");
  const [variant, setVariant] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [selected, setSelected] = useState<Sample | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [apiOnline, setApiOnline] = useState(false);
  const [heldout, setHeldout] = useState<HeldoutSummary | null>(null);
  const [heldoutError, setHeldoutError] = useState("");
  const replayAudit =
    heldout?.latestLiveV5Replay ?? heldout?.latestReplay ?? null;
  const replayIsLiveV5 = Boolean(heldout?.latestLiveV5Replay);
  const [activeHeldoutId, setActiveHeldoutId] = useState("");
  const [heldoutEvidence, setHeldoutEvidence] =
    useState<LocalEvidenceDetail | null>(null);
  const [heldoutEvidenceLoading, setHeldoutEvidenceLoading] = useState(false);
  const [heldoutEvidenceError, setHeldoutEvidenceError] = useState("");
  const [evidenceMode, setEvidenceMode] =
    useState<"heldout" | "templates" | "cccd">(
      SHOW_HELDOUT ? "heldout" : "templates",
    );
  const [evidenceInspectorView, setEvidenceInspectorView] =
    useState<"fields" | "json">("fields");
  const [activeCccdSessionId, setActiveCccdSessionId] = useState("");
  const [templateSessions, setTemplateSessions] =
    useState<TemplateSessionSummary[]>([]);
  const [activeTemplateSessionId, setActiveTemplateSessionId] = useState("");
  const [templateEvidenceResult, setTemplateEvidenceResult] =
    useState<TemplateProcessingResult | null>(null);
  const [templateEvidenceLoading, setTemplateEvidenceLoading] = useState(false);
  const [templateEvidenceError, setTemplateEvidenceError] = useState("");
  const [cccdEvidenceResult, setCccdEvidenceResult] =
    useState<UserResult | null>(null);
  const [cccdEvidenceReview, setCccdEvidenceReview] =
    useState<Phase10Review | null>(null);
  const [cccdEvidenceLoading, setCccdEvidenceLoading] = useState(false);
  const [cccdEvidenceError, setCccdEvidenceError] = useState("");
  const [viewProfile, setViewProfile] = useState<"phase7" | "baseline">("phase7");
  const [processingMode, setProcessingMode] =
    useState<"template" | "legacy">("template");
  const [supportedTemplates, setSupportedTemplates] =
    useState<SupportedTemplate[]>([]);
  const [templateResult, setTemplateResult] =
    useState<TemplateProcessingResult | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [userResult, setUserResult] = useState<UserResult | null>(null);
  const [userSessions, setUserSessions] = useState<UserSessionSummary[]>([]);
  const [showSessionHistory, setShowSessionHistory] = useState(false);
  const [activeUserPage, setActiveUserPage] = useState(0);
  const [deleteArmed, setDeleteArmed] = useState(false);
  const [textView, setTextView] = useState<"corrected" | "raw">("corrected");
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [phase10Review, setPhase10Review] = useState<Phase10Review | null>(null);
  const [reviewDraft, setReviewDraft] = useState<Array<{ pageIndex: number; text: string }>>(
    [],
  );
  const [identityFieldDraft, setIdentityFieldDraft] = useState<Record<string, string>>(
    {},
  );
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [phase15FieldDraft, setPhase15FieldDraft] = useState<Record<string, string>>(
    {},
  );
  const [phase15ReviewAssertions, setPhase15ReviewAssertions] = useState({
    comparedWithSource: false,
    allFieldsChecked: false,
  });
  const [isSavingPhase15Review, setIsSavingPhase15Review] = useState(false);
  const [isRunningChallenger, setIsRunningChallenger] = useState(false);
  const [isRunningHybrid, setIsRunningHybrid] = useState(false);
  const [phase14, setPhase14] = useState<Phase14Benchmark | null>(null);
  const [phase14CaseIndex, setPhase14CaseIndex] = useState(0);
  const [phase14GroundTruth, setPhase14GroundTruth] = useState("");
  const [phase14Assertions, setPhase14Assertions] = useState({
    comparedWithCrop: false,
    allTextChecked: false,
  });
  const [isSavingPhase14, setIsSavingPhase14] = useState(false);
  const phase14PendingCases = useMemo(
    () => pendingReviewCases(phase14?.cases, phase14?.lineReviews),
    [phase14],
  );
  const [reviewAssertions, setReviewAssertions] = useState({
    comparedWithImage: false,
    allTextChecked: false,
    acceptUnchangedDraft: false,
  });

  const setLoadedUserResult = (result: UserResult | null) => {
    setUserResult(result);
    const phase = result?.phase15;
    if (!phase) {
      setPhase15FieldDraft({});
      setPhase15ReviewAssertions({
        comparedWithSource: false,
        allFieldsChecked: false,
      });
      return;
    }
    setPhase15FieldDraft(
      Object.fromEntries(
        Object.entries(phase.extraction.fields).map(([name, field]) => [
          name,
          field.normalizedValue === null || field.normalizedValue === undefined
            ? field.value === null || field.value === undefined
              ? ""
              : String(field.value)
            : String(field.normalizedValue),
        ]),
      ),
    );
    const alreadyReviewed = phase.review?.reviewStatus === "USER_REVIEWED";
    setPhase15ReviewAssertions({
      comparedWithSource: alreadyReviewed,
      allFieldsChecked: alreadyReviewed,
    });
  };

  const loadPhase10Review = async (sessionId: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/user/review?id=${encodeURIComponent(sessionId)}`,
      );
      if (!response.ok) throw new Error("Review unavailable");
      const payload = normalizePhase10Review(
        (await response.json()) as Phase10Review,
      );
      setPhase10Review(payload);
      setReviewDraft(
        payload.groundTruth?.pages.map((page) => ({ ...page })) ??
          payload.draftPages.map((page) => ({ ...page })),
      );
      setIdentityFieldDraft(
        payload.groundTruth?.identityFields ?? payload.identityFieldDraft,
      );
      setReviewAssertions({
        comparedWithImage:
          payload.groundTruth?.verificationAssertions?.comparedWithImage ?? false,
        allTextChecked:
          payload.groundTruth?.verificationAssertions?.allTextChecked ?? false,
        acceptUnchangedDraft:
          payload.groundTruth?.verificationAssertions?.acceptUnchangedDraft ?? false,
      });
    } catch {
      setPhase10Review(null);
      setReviewDraft([]);
      setIdentityFieldDraft({});
    }
  };

  const refreshUserSessions = () => {
    fetch(`${API_BASE}/user/sessions`)
      .then((response) => {
        if (!response.ok) throw new Error("offline");
        return response.json();
      })
      .then((payload: { sessions: UserSessionSummary[] }) =>
        setUserSessions(payload.sessions),
      )
      .catch(() => setUserSessions([]));
  };

  const refreshTemplateSessions = () => {
    fetch(`${API_BASE}/api/documents/sessions`)
      .then((response) => {
        if (!response.ok) throw new Error("Template sessions unavailable");
        return response.json();
      })
      .then((payload: { sessions: TemplateSessionSummary[] }) => {
        setTemplateSessions(payload.sessions);
        setActiveTemplateSessionId((current) =>
          payload.sessions.some((session) => session.documentId === current)
            ? current
            : payload.sessions[0]?.documentId ?? "",
        );
      })
      .catch(() => {
        setTemplateSessions([]);
        setActiveTemplateSessionId("");
      });
  };

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((response) => {
        if (!response.ok) throw new Error("offline");
        setApiOnline(true);
      })
      .catch(() => setApiOnline(false));
    fetch(`${API_BASE}/api/templates`)
      .then((response) => {
        if (!response.ok) throw new Error("Template registry unavailable");
        return response.json();
      })
      .then((payload: { templates: SupportedTemplate[] }) =>
        setSupportedTemplates(payload.templates),
      )
      .catch(() => setSupportedTemplates([]));
    if (SHOW_HELDOUT) {
      fetch(`${API_BASE}/heldout/summary`)
        .then((response) => {
          if (!response.ok) throw new Error("Real held-out unavailable");
          return response.json();
        })
        .then((payload: HeldoutSummary) => {
          setApiOnline(true);
          setHeldout(payload);
          setHeldoutError("");
          setActiveHeldoutId(
            payload.documents.find((item) => item.previewAvailable)?.documentId ??
              payload.documents[0]?.documentId ??
              "",
          );
        })
        .catch(() => {
          setHeldout(null);
          setHeldoutError(
            "Chưa kết nối được tập held-out thật đã xác nhận quyền xử lý.",
          );
        });
    }
    refreshUserSessions();
    refreshTemplateSessions();
    fetch(`${API_BASE}/phase14/benchmark`)
      .then((response) => {
        if (!response.ok) throw new Error("Phase 14 unavailable");
        return response.json();
      })
      .then((payload: Phase14Benchmark) => {
        const resume = resumePendingReview(
          payload.cases,
          payload.lineReviews,
        );
        setPhase14(payload);
        setPhase14CaseIndex(resume.index);
        if (resume.active) {
          setPhase14GroundTruth(resume.active.groundTruth);
        } else {
          setPhase14GroundTruth("");
        }
      })
      .catch(() => setPhase14(null));
  }, []);

  useEffect(() => {
    if (!SHOW_HELDOUT || !activeHeldoutId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale evidence when the list becomes empty.
      setHeldoutEvidence(null);
      return;
    }
    let cancelled = false;
    setHeldoutEvidenceLoading(true);
    setHeldoutEvidenceError("");
    fetch(
      `${API_BASE}/heldout/evidence?id=${encodeURIComponent(activeHeldoutId)}`,
    )
      .then((response) => {
        if (!response.ok) throw new Error("Không tải được schema held-out");
        return response.json();
      })
      .then((payload: LocalEvidenceDetail) => {
        if (!cancelled) setHeldoutEvidence(payload);
      })
      .catch(() => {
        if (!cancelled) {
          setHeldoutEvidence(null);
          setHeldoutEvidenceError(
            "Không đọc được Ground Truth và prediction cục bộ.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setHeldoutEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeHeldoutId]);

  const selectPhase14Case = (index: number) => {
    if (
      !phase14 ||
      index < 0 ||
      index >= phase14PendingCases.length
    ) {
      return;
    }
    const nextCase = phase14PendingCases[index];
    setPhase14CaseIndex(index);
    setPhase14GroundTruth(nextCase.groundTruth);
    setPhase14Assertions({
      comparedWithCrop: false,
      allTextChecked: false,
    });
  };

  const savePhase14Review = async () => {
    if (!phase14 || isSavingPhase14) return;
    const activeCase = phase14PendingCases[phase14CaseIndex];
    if (!activeCase) return;
    setIsSavingPhase14(true);
    setUploadError("");
    try {
      const response = await fetch(`${API_BASE}/phase14/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          caseId: activeCase.caseId,
          groundTruth: phase14GroundTruth,
          ...phase14Assertions,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Không lưu được Ground Truth dòng");
      }
      const nextPendingCases = phase14PendingCases.filter(
        (item) => item.caseId !== activeCase.caseId,
      );
      const nextIndex = Math.min(
        phase14CaseIndex,
        Math.max(0, nextPendingCases.length - 1),
      );
      setPhase14((current) =>
        current
          ? {
              ...current,
              reviewedLineCount: payload.reviewedCount,
              lineReviews: {
                ...current.lineReviews,
                [activeCase.caseId]: {
                  groundTruth: phase14GroundTruth,
                  reviewedAt: new Date().toISOString(),
                  comparedWithCrop: true,
                  allTextChecked: true,
                },
              },
            }
          : current,
      );
      setPhase14CaseIndex(nextIndex);
      setPhase14GroundTruth(
        nextPendingCases[nextIndex]?.groundTruth ?? "",
      );
      setPhase14Assertions({
        comparedWithCrop: false,
        allTextChecked: false,
      });
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : "Không lưu được Ground Truth dòng",
      );
    } finally {
      setIsSavingPhase14(false);
    }
  };

  useEffect(() => {
    if (!selected) return;
    fetch(
      `${API_BASE}/detail?id=${encodeURIComponent(selected.sampleId)}&profile=${viewProfile}`,
    )
      .then((response) => {
        if (!response.ok) throw new Error("Không tải được Native JSON");
        return response.json();
      })
      .then((payload: Detail) => {
        setDetail(payload);
        setDetailError("");
      })
      .catch(() => {
        setDetail(null);
        setDetailError("API local chưa chạy hoặc sample không tồn tại.");
      });
  }, [selected, viewProfile]);

  const types = useMemo(
    () => Array.from(new Set(data.samples.map((sample) => sample.documentType))).sort(),
    [data.samples],
  );
  const variants = useMemo(
    () => Array.from(new Set(data.samples.map((sample) => sample.variant))).sort(),
    [data.samples],
  );
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return data.samples.filter((sample) => {
      const matchesQuery =
        !normalizedQuery ||
        sample.sampleId.toLowerCase().includes(normalizedQuery) ||
        sample.documentId.toLowerCase().includes(normalizedQuery);
      const matchesType = type === "ALL" || sample.documentType === type;
      const matchesVariant = variant === "ALL" || sample.variant === variant;
      const matchesStatus =
        status === "ALL" ||
        (status === "SUCCESS" && sample.ocrSuccess) ||
        (status === "FAILED" && !sample.ocrSuccess);
      return matchesQuery && matchesType && matchesVariant && matchesStatus;
    });
  }, [data.samples, query, type, variant, status]);

  const typePerformance = useMemo(() => {
    return types
      .filter((name) => name !== "PUBLIC_OCR")
      .map((name) => {
        const rows = data.samples.filter(
          (sample) => sample.documentType === name && sample.cer !== null,
        );
        const cer = rows.reduce((sum, row) => sum + (row.cer ?? 0), 0) / rows.length;
        return { name, cer, samples: rows.length };
      })
      .sort((a, b) => a.cer - b.cer);
  }, [data.samples, types]);

  const successRate = data.summary.ocrSuccessCount / data.summary.nativeJsonCount;
  const reviewDraftIsUnchanged =
    phase10Review !== null &&
    reviewDraft.length === phase10Review.draftPages.length &&
    reviewDraft.every(
      (page, index) =>
        page.text.replace(/\s+/g, " ").trim().toLocaleLowerCase("vi") ===
        (phase10Review.draftPages[index]?.text ?? "")
          .replace(/\s+/g, " ")
          .trim()
          .toLocaleLowerCase("vi"),
    );

  const submitUpload = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!uploadFile || isUploading) return;
    if (
      processingMode === "template" &&
      !uploadFile.name.toLocaleLowerCase("vi").endsWith(".docx")
    ) {
      setUploadError("Template-first hiện chỉ hỗ trợ file DOCX có text.");
      return;
    }
    setIsUploading(true);
    setUploadError("");
    setLoadedUserResult(null);
    setTemplateResult(null);
    setDeleteArmed(false);
    const formData = new FormData();
    formData.append("file", uploadFile);
    try {
      const endpoint =
        processingMode === "template"
          ? "/api/documents/process"
          : "/user/upload";
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        body: formData,
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) {
        const errorCode =
          typeof payload.errorCode === "string"
            ? payload.errorCode
            : typeof payload.error === "string"
              ? payload.error
              : "LOCAL_PROCESSING_FAILED";
        throw new Error(
          processingMode === "template"
            ? `Không xử lý được biểu mẫu: ${errorCode}`
            : `OCR local thất bại: ${errorCode}`,
        );
      }
      if (processingMode === "template") {
        const result = payload as TemplateProcessingResult;
        setTemplateResult(result);
        setActiveTemplateSessionId(result.data.documentId);
        refreshTemplateSessions();
      } else {
        const userPayload = payload as UserResult;
        setLoadedUserResult(userPayload);
        setActiveUserPage(0);
        setTextView("corrected");
        loadPhase10Review(userPayload.sessionId);
        refreshUserSessions();
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Không thể xử lý file");
    } finally {
      setIsUploading(false);
    }
  };

  const loadUserSession = async (sessionId: string) => {
    setUploadError("");
    setDeleteArmed(false);
    try {
      const response = await fetch(
        `${API_BASE}/user/session?id=${encodeURIComponent(sessionId)}`,
      );
      if (!response.ok) throw new Error("Không tải được session");
      const payload = (await response.json()) as UserResult;
      setLoadedUserResult(payload);
      setActiveUserPage(0);
      setTextView("corrected");
      loadPhase10Review(payload.sessionId);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Không tải được session");
    }
  };

  const openEvidenceSession = async (sessionId: string) => {
    await loadUserSession(sessionId);
    window.location.hash = "upload";
  };

  const reprocessPhase9 = async () => {
    if (!userResult || isReprocessing) return;
    setIsReprocessing(true);
    setUploadError("");
    try {
      const response = await fetch(
        `${API_BASE}/user/reprocess?id=${encodeURIComponent(userResult.sessionId)}`,
        { method: "POST" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Phase 9 thất bại");
      setLoadedUserResult(payload as UserResult);
      setActiveUserPage(0);
      setTextView("corrected");
      loadPhase10Review((payload as UserResult).sessionId);
      refreshUserSessions();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Không thể chạy Phase 9");
    } finally {
      setIsReprocessing(false);
    }
  };

  const savePhase10Review = async () => {
    if (!userResult || !reviewDraft.length || isSavingReview) return;
    setIsSavingReview(true);
    setUploadError("");
    try {
      const response = await fetch(
        `${API_BASE}/user/review?id=${encodeURIComponent(userResult.sessionId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            pages: reviewDraft,
            assertions: reviewAssertions,
            identityFields:
              userResult.phase11?.identityCard ? identityFieldDraft : undefined,
          }),
        },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Không lưu được ground truth");
      setPhase10Review(normalizePhase10Review(payload as Phase10Review));
      refreshUserSessions();
    } catch (error) {
      setUploadError(
        error instanceof Error ? error.message : "Không lưu được ground truth",
      );
    } finally {
      setIsSavingReview(false);
    }
  };

  const savePhase15Review = async () => {
    if (!userResult?.phase15 || isSavingPhase15Review) return;
    setIsSavingPhase15Review(true);
    setUploadError("");
    try {
      const response = await fetch(
        `${API_BASE}/user/phase15-review?id=${encodeURIComponent(
          userResult.sessionId,
        )}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fields: phase15FieldDraft,
            assertions: phase15ReviewAssertions,
          }),
        },
      );
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Không lưu được review Phase 15");
      }
      setLoadedUserResult(payload as UserResult);
      refreshUserSessions();
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : "Không lưu được review Phase 15",
      );
    } finally {
      setIsSavingPhase15Review(false);
    }
  };

  const runEasyOcrChallenger = async () => {
    if (!userResult || isRunningChallenger) return;
    setIsRunningChallenger(true);
    setUploadError("");
    try {
      const response = await fetch(
        `${API_BASE}/user/easyocr?id=${encodeURIComponent(userResult.sessionId)}`,
        { method: "POST" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "EasyOCR thất bại");
      const review = normalizePhase10Review(payload as Phase10Review);
      setPhase10Review(review);
      if (!review.groundTruth && review.challenger.draftPages) {
        setReviewDraft(review.challenger.draftPages.map((page) => ({ ...page })));
      }
      if (!review.groundTruth && review.challenger.identityCard) {
        setIdentityFieldDraft(
          Object.fromEntries(
            Object.entries(review.challenger.identityCard.fields).map(
              ([field, item]) => [field, item.value ?? ""],
            ),
          ),
        );
      }
      setReviewAssertions({
        comparedWithImage: false,
        allTextChecked: false,
        acceptUnchangedDraft: false,
      });
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "EasyOCR thất bại");
    } finally {
      setIsRunningChallenger(false);
    }
  };

  const runHybridOcr = async () => {
    if (!userResult || isRunningHybrid) return;
    setIsRunningHybrid(true);
    setUploadError("");
    try {
      const response = await fetch(
        `${API_BASE}/user/controlled-pilot?id=${encodeURIComponent(userResult.sessionId)}`,
        { method: "POST" },
      );
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Phase 14.2 controlled pilot thất bại");
      }
      setPhase10Review(normalizePhase10Review(payload as Phase10Review));
    } catch (error) {
      setUploadError(
        error instanceof Error ? error.message : "Phase 14.2 controlled pilot thất bại",
      );
    } finally {
      setIsRunningHybrid(false);
    }
  };

  const deleteTemplateSession = async () => {
    const documentId = templateResult?.data.documentId;
    if (!documentId) return;
    if (!deleteArmed) {
      setDeleteArmed(true);
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE}/user/session?id=${encodeURIComponent(documentId)}`,
        { method: "DELETE" },
      );
      if (!response.ok) throw new Error("Không xóa được kết quả Template-first");
      setTemplateResult(null);
      setUploadFile(null);
      setDeleteArmed(false);
      refreshTemplateSessions();
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : "Không xóa được kết quả Template-first",
      );
    }
  };

  const deleteUserSession = async () => {
    if (!userResult) return;
    if (!deleteArmed) {
      setDeleteArmed(true);
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE}/user/session?id=${encodeURIComponent(userResult.sessionId)}`,
        { method: "DELETE" },
      );
      if (!response.ok) throw new Error("Không xóa được session");
      setLoadedUserResult(null);
      setUploadFile(null);
      setDeleteArmed(false);
      setPhase10Review(null);
      setReviewDraft([]);
      setIdentityFieldDraft({});
      refreshUserSessions();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Không xóa được session");
    }
  };

  const activePhase14Case =
    phase14PendingCases[phase14CaseIndex] ?? null;
  const phase14PaddleMetrics = phase14?.profiles.paddle_detector_raw;
  const phase14BestEasyMetrics = phase14
    ? phase14.profiles[phase14.selection.bestEasyProfile]
    : null;
  const phase14VietMetrics = phase14?.phase14_3
    ? phase14.profiles[
        phase14.phase14_3.selected.selectedPrimaryProfile
      ]
    : phase14?.profiles.vietocr_best_crop;
  const featuredSample =
    data.samples.find((sample) => sample.sampleId === "cv__HR-CV-0001_page_0") ??
    data.samples[0];
  const reviewedCccdSessions = useMemo(() => {
    const seenFiles = new Set<string>();
    return userSessions
      .filter((session) => {
        const fileKey = session.originalFileName
          .trim()
          .toLocaleLowerCase("vi");
        if (
          session.documentType !== "IDENTITY_DOCUMENT" ||
          !session.reviewed ||
          /synthetic|demo/i.test(fileKey) ||
          seenFiles.has(fileKey)
        ) {
          return false;
        }
        seenFiles.add(fileKey);
        return true;
      })
      .sort((left, right) =>
        (right.phase11Version ?? "").localeCompare(
          left.phase11Version ?? "",
          undefined,
          { numeric: true, sensitivity: "base" },
        ),
      );
  }, [userSessions]);
  const activeTemplateSession =
    templateSessions.find(
      (session) => session.documentId === activeTemplateSessionId,
    ) ??
    templateSessions[0] ??
    null;
  const activeTemplateEvidenceId = activeTemplateSession?.documentId ?? "";
  useEffect(() => {
    if (!activeTemplateEvidenceId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale evidence when the selected template result disappears.
      setTemplateEvidenceResult(null);
      return;
    }
    let cancelled = false;
    setTemplateEvidenceLoading(true);
    setTemplateEvidenceError("");
    fetch(
      `${API_BASE}/api/documents/result?id=${encodeURIComponent(
        activeTemplateEvidenceId,
      )}`,
    )
      .then((response) => {
        if (!response.ok) throw new Error("Template evidence unavailable");
        return response.json() as Promise<TemplateProcessingResult>;
      })
      .then((result) => {
        if (!cancelled) setTemplateEvidenceResult(result);
      })
      .catch(() => {
        if (cancelled) return;
        setTemplateEvidenceResult(null);
        setTemplateEvidenceError(
          "Không đọc được metadata và JSON của biểu mẫu này.",
        );
      })
      .finally(() => {
        if (!cancelled) setTemplateEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTemplateEvidenceId]);
  const activeCccdSession =
    reviewedCccdSessions.find(
      (session) => session.sessionId === activeCccdSessionId,
    ) ??
    reviewedCccdSessions[0] ??
    null;
  const activeCccdEvidenceId = activeCccdSession?.sessionId ?? "";
  useEffect(() => {
    if (!activeCccdEvidenceId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale CCCD evidence when the selected session disappears.
      setCccdEvidenceResult(null);
      setCccdEvidenceReview(null);
      return;
    }
    let cancelled = false;
    setCccdEvidenceLoading(true);
    setCccdEvidenceError("");
    Promise.all([
      fetch(
        `${API_BASE}/user/session?id=${encodeURIComponent(
          activeCccdEvidenceId,
        )}`,
      ),
      fetch(
        `${API_BASE}/user/review?id=${encodeURIComponent(
          activeCccdEvidenceId,
        )}`,
      ),
    ])
      .then(async ([resultResponse, reviewResponse]) => {
        if (!resultResponse.ok || !reviewResponse.ok) {
          throw new Error("CCCD evidence unavailable");
        }
        return Promise.all([
          resultResponse.json() as Promise<UserResult>,
          reviewResponse.json() as Promise<Phase10Review>,
        ]);
      })
      .then(([result, review]) => {
        if (cancelled) return;
        setCccdEvidenceResult(result);
        setCccdEvidenceReview(normalizePhase10Review(review));
      })
      .catch(() => {
        if (cancelled) return;
        setCccdEvidenceResult(null);
        setCccdEvidenceReview(null);
        setCccdEvidenceError(
          "Không đọc được Ground Truth và JSON của CCCD này.",
        );
      })
      .finally(() => {
        if (!cancelled) setCccdEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCccdEvidenceId]);
  const activeCccdEvidence = useMemo<LocalEvidenceDetail | null>(() => {
    if (!cccdEvidenceResult || !activeCccdSession) return null;
    const phase15 = cccdEvidenceResult.phase15;
    const identityCard = cccdEvidenceResult.phase11?.identityCard;
    return {
      schemaVersion: "ocr-lab-session-evidence/1.0.0",
      documentId: cccdEvidenceResult.sessionId,
      documentFamily: "IDENTITY_DOCUMENT",
      documentType:
        phase15?.classification.documentType ??
        cccdEvidenceResult.document.documentType,
      schemaRef:
        cccdEvidenceResult.phase11_5
          ? "schemas/vietnam_identity_card_phase11_5.schema.json"
          : phase15?.classification.schemaRef ??
            "schemas/business_document.schema.json",
      containsRealPII: true,
      localOnly: true,
      groundTruth: {
        reviewStatus: cccdEvidenceReview?.reviewStatus ?? "DRAFT",
        fields: cccdEvidenceReview?.groundTruth?.identityFields ?? {},
      },
      prediction: {
        classification: phase15?.classification ?? null,
        recognition: cccdEvidenceResult.phase14_8?.summary ?? null,
        fields: identityCard?.fields ?? phase15?.extraction.fields ?? {},
        summary: identityCard?.summary ?? phase15?.extraction.summary ?? null,
      },
      predictionLabel: `CCCD Phase ${phase11Label(
        cccdEvidenceResult,
      )} · ${cccdEvidenceResult.processing.ocrVersion}`,
      predictionNotice:
        "Prediction từ pipeline CCCD chuyên biệt; Ground Truth đã review được giữ nguyên.",
    };
  }, [activeCccdSession, cccdEvidenceResult, cccdEvidenceReview]);
  const activeHeldoutDocument =
    SHOW_HELDOUT
      ? heldout?.documents.find(
          (document) => document.documentId === activeHeldoutId,
        ) ?? null
      : null;
  const unifiedIdp = userResult?.phase15 ?? userResult?.phase12;

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Về đầu trang">
          <span className="brand-mark">HR</span>
          <span>OCR LAB</span>
        </a>
        <nav aria-label="Điều hướng chính">
          {SHOW_HELDOUT ? <a href="#metrics">Held-out thật</a> : null}
          <a href="#upload">OCR tài liệu thật</a>
          <a href="#explorer">Tài liệu &amp; CCCD</a>
          <a href="#phases">Policy</a>
          <a href="#next">Tiếp theo</a>
        </nav>
        <span className={`live ${apiOnline ? "online" : ""}`}>
          <i />
          {apiOnline ? "Local API online" : "Metrics only"}
        </span>
      </header>

      <section className="hero" id="overview">
        <div className="hero-copy">
          <p className="eyebrow">HR DOCUMENT INTELLIGENCE LAB</p>
          <h1>
            Đọc tài liệu.
            <span> Giữ bằng chứng.</span>
          </h1>
          <p className="hero-lead">
            OCR tiếng Việt, bằng chứng từng trường và human review, chạy hoàn toàn
            trên máy của bạn.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#upload">
              Thử tài liệu thật
            </a>
            <a className="text-button" href="#product">
              Xem sản phẩm <span>→</span>
            </a>
          </div>
        </div>
        <aside className="hero-product" aria-label="Khả năng xử lý biểu mẫu HCNS">
          <div className="hero-product-frame product-showcase" data-testid="product-showcase">
            <header>
              <div>
                <span>ĐANG SẴN SÀNG</span>
                <strong>Biểu mẫu HCNS chuẩn</strong>
              </div>
              <b>LOCAL</b>
            </header>
            <div className="product-flow" aria-label="Luồng xử lý Template-first">
              <span>DOCX</span><i>→</i><span>Template</span><i>→</i><span>JSON</span>
            </div>
            <div className="product-template-list">
              <article>
                <span>LEAVE_REQUEST</span>
                <strong>Đơn xin nghỉ phép</strong>
                <small>Native DOCX · validation theo mẫu</small>
              </article>
              <article>
                <span>OVERTIME_REQUEST</span>
                <strong>Đơn xin tăng ca</strong>
                <small>Native DOCX · quality routing</small>
              </article>
            </div>
            <div className="product-showcase-footer">
              <span>Không tự suy đoán field thiếu</span>
              <strong>AUTO_CONTINUE / MANUAL_REVIEW</strong>
            </div>
          </div>
          <p>Đầu vào có format sẵn, kết quả có schema và JSON để kiểm tra.</p>
        </aside>
      </section>

      {SHOW_HELDOUT ? (
        <section className="proof-strip" aria-label="Bằng chứng vận hành">
          <div>
            <span>Bằng chứng thật</span>
            <strong>
              {heldout?.documentCount ?? "—"} HR +{" "}
              {reviewedCccdSessions.length} CCCD
            </strong>
          </div>
          <div>
            <span>Phạm vi</span>
            <strong>
              {heldout ? Object.keys(heldout.byFamily).length : "—"} HR + ID
            </strong>
          </div>
          <div>
            <span>Field Exact</span>
            <strong>{pct(heldout?.overall.fieldExactMatchRate ?? null)}</strong>
          </div>
          <div>
            <span>Quyết định</span>
            <strong>{heldout?.decision.production ?? "Chưa có"}</strong>
          </div>
        </section>
      ) : null}

      <section className="section product-section" id="product">
        <figure className="product-context">
          {activeHeldoutDocument?.previewAvailable ? (
            <img
              src={`${API_BASE}/heldout/document?id=${encodeURIComponent(
                activeHeldoutDocument.documentId,
              )}&mode=preview`}
              alt={`Tài liệu held-out thật ${activeHeldoutDocument.documentId}`}
            />
          ) : (
            <div className="native-heldout-file">
              <strong>Trích xuất tài liệu hành chính nhân sự</strong>
              <p>Native parsing, OCR, quality gate và human review.</p>
            </div>
          )}
        </figure>
        <div className="product-story">
          <h2>Một luồng xử lý, bằng chứng đi cùng dữ liệu.</h2>
          <p>
            Sản phẩm nhận ảnh, PDF, DOCX và XLSX, sau đó chọn native extraction hoặc
            OCR phù hợp trước khi tạo JSON có thể kiểm tra.
          </p>
          <dl className="product-capabilities">
            <div>
              <dt>Nhận tài liệu</dt>
              <dd>Ảnh và PDF scan đi qua OCR. DOCX và XLSX ưu tiên dữ liệu gốc.</dd>
            </div>
            <div>
              <dt>Giữ bằng chứng</dt>
              <dd>Mỗi kết quả gắn với trang, text, confidence và bounding box.</dd>
            </div>
            <div>
              <dt>Kiểm duyệt ngoại lệ</dt>
              <dd>Trường chưa chắc chắn được chuyển sang needs_review để người dùng xác nhận.</dd>
            </div>
          </dl>
          <a className="primary-button product-cta" href="#upload">
            Thử tài liệu thật
          </a>
        </div>
      </section>

      <section className="section upload-section" id="upload">
        <div className="section-heading">
          <div>
            <p className="eyebrow">LOCAL PRIVATE OCR</p>
            <h2>Đưa tài liệu thật vào</h2>
          </div>
          <p>
            File, OCR text và JSON chỉ nằm trên máy này. Không upload cloud, không
            telemetry, không ghi PII vào log hoặc Git.
          </p>
        </div>

        {false && phase14 && (
          <div className="phase10-review">
            <div className="phase10-title">
              <div>
                <p className="eyebrow">PHASE 14.4 / GROUND TRUTH EXPANSION</p>
                <h3>Xác nhận hàng đợi crop từ 15 tài liệu</h3>
              </div>
              <span className="draft">
                {phase14.reviewedLineCount}/{phase14.lineCount} VERIFIED
              </span>
            </div>
            <p className="review-help">
              {phase14.secondRecognizerBenchmark
                ? `Benchmark cuối đã mở khóa trên ${phase14.secondRecognizerBenchmark.documentCount} tài liệu và ${phase14.secondRecognizerBenchmark.lineCount} crop Ground Truth.`
                : `Metric hiện tại vẫn cố định trên ${phase14.evaluationLineCount ?? 77} crop; queue mở rộng có ${phase14.groundTruthExpansion?.documentCount ?? phase14.documentCount} tài liệu và ${phase14.lineCount} dòng.`}
              VietOCR đang tốt nhất ở cấp dòng nhưng chưa production-ready.
              EasyOCR exact agreement là verifier auto-accept an toàn hiện tại.
              Paddle chỉ là fallback candidate cho human review; mọi bất đồng
              vẫn chuyển sang needs_review.
            </p>
            {phase14.secondRecognizer && (
              <p className="review-help">
                Recognizer thứ hai: {phase14.secondRecognizer.config} —{" "}
                {phase14.secondRecognizer.weightAvailable
                  ? "weight local đã sẵn sàng"
                  : "chưa có weight local"}. Benchmark sẽ mở khóa khi queue đạt{" "}
                {phase14.lineCount}/{phase14.lineCount}; hiện còn{" "}
                {phase14.secondRecognizer.blockedByPendingReviewCount} dòng cần
                xác nhận.
              </p>
            )}
            {phase14.blindedPrecompute && (
              <p className="review-help">
                Hai recognizer đã chạy ngầm trên{" "}
                {phase14.blindedPrecompute.lineCount} crop và artifact đã khóa
                theo queue digest. Prediction đang được ẩn để tránh annotation
                bias; chỉ mở khóa sau khi Ground Truth đạt{" "}
                {phase14.lineCount}/{phase14.lineCount}.
              </p>
            )}
            <div className="evaluation-grid phase14-evaluation-grid">
              <div>
                <span>Paddle raw</span>
                <strong>
                  Exact {pct(phase14PaddleMetrics?.exactMatchRate ?? null)}
                </strong>
                <small>CER {decimal(phase14PaddleMetrics?.cer ?? null)}</small>
              </div>
              <div>
                <span>EasyOCR best</span>
                <strong>
                  Exact {pct(phase14BestEasyMetrics?.exactMatchRate ?? null)}
                </strong>
                <small>CER {decimal(phase14BestEasyMetrics?.cer ?? null)}</small>
              </div>
              <div>
                <span>VietOCR best</span>
                <strong>
                  Exact {pct(phase14VietMetrics?.exactMatchRate ?? null)}
                </strong>
                <small>CER {decimal(phase14VietMetrics?.cer ?? null)}</small>
              </div>
              <div>
                <span>Promotion</span>
                <strong>{phase14.selection.promotionDecision}</strong>
                <small>
                  {phase14.selection.productionDecision ?? phase14.alignmentStatus}
                </small>
              </div>
            </div>
            {phase14.controlledPilot && (
              <div className="evaluation-grid phase14-evaluation-grid">
                <div>
                  <span>Controlled sessions</span>
                  <strong>{phase14.controlledPilot.sessionCount}</strong>
                  <small>
                    {phase14.controlledPilot.failedSessionCount} failed
                  </small>
                </div>
                <div>
                  <span>Pilot crops</span>
                  <strong>{phase14.controlledPilot.summary.cropCount}</strong>
                  <small>authorized local sessions</small>
                </div>
                <div>
                  <span>Auto-accepted</span>
                  <strong>
                    {phase14.controlledPilot.summary.acceptedLineCount}
                  </strong>
                  <small>
                    {pct(phase14.controlledPilot.summary.acceptanceRate)}
                  </small>
                </div>
                <div>
                  <span>Needs review</span>
                  <strong>
                    {phase14.controlledPilot.summary.needsReviewLineCount}
                  </strong>
                  <small>
                    {phase14.controlledPilot.decision.productionStatus}
                  </small>
                </div>
              </div>
            )}
            {phase14.phase14_3 && (
              <div className="evaluation-grid phase14-evaluation-grid">
                <div>
                  <span>Selected crop</span>
                  <strong>
                    {phase14.phase14_3.selected.selectedCropProfile}
                  </strong>
                  <small>VietOCR vgg_seq2seq</small>
                </div>
                <div>
                  <span>Baseline errors</span>
                  <strong>
                    {phase14.phase14_3.baselineFailureCount}/
                    {phase14.evaluationLineCount ?? 77}
                  </strong>
                  <small>
                    Missing/substituted{" "}
                    {
                      phase14.phase14_3.errorAnalysis.categoryCounts
                        .missing_or_substituted_characters
                    }
                  </small>
                </div>
                <div>
                  <span>Crop recovery ceiling</span>
                  <strong>
                    {
                      phase14.phase14_3.errorAnalysis
                        .oracleRecoveryUpperBound.otherVietocrCrop
                    }
                  </strong>
                  <small>analysis only, not a runtime rule</small>
                </div>
                <div>
                  <span>Review fallback</span>
                  <strong>
                    {phase14.phase14_3.selected.fallbackRecognizer}
                  </strong>
                  <small>
                    auto verifier:{" "}
                    {phase14.phase14_3.selected.autoAcceptVerifier ?? "none"}
                  </small>
                </div>
              </div>
            )}
            {phase14.secondRecognizerBenchmark && (
              <div className="evaluation-grid phase14-evaluation-grid">
                <div>
                  <span>Seq2seq</span>
                  <strong>
                    Exact{" "}
                    {pct(
                      phase14.secondRecognizerBenchmark.profiles
                        .vietocr_vgg_seq2seq.exactMatchRate,
                    )}
                  </strong>
                  <small>
                    CER{" "}
                    {decimal(
                      phase14.secondRecognizerBenchmark.profiles
                        .vietocr_vgg_seq2seq.cer,
                    )}
                  </small>
                </div>
                <div>
                  <span>Transformer</span>
                  <strong>
                    Exact{" "}
                    {pct(
                      phase14.secondRecognizerBenchmark.profiles
                        .vietocr_vgg_transformer.exactMatchRate,
                    )}
                  </strong>
                  <small>
                    CER{" "}
                    {decimal(
                      phase14.secondRecognizerBenchmark.profiles
                        .vietocr_vgg_transformer.cer,
                    )}
                  </small>
                </div>
                <div>
                  <span>Selected primary</span>
                  <strong>
                    {
                      phase14.secondRecognizerBenchmark.decision
                        .selectedPrimary
                    }
                  </strong>
                  <small>
                    {
                      phase14.secondRecognizerBenchmark.predictionSource
                    }
                  </small>
                </div>
                <div>
                  <span>Challenger</span>
                  <strong>
                    {
                      phase14.secondRecognizerBenchmark.decision
                        .challengerDecision
                    }
                  </strong>
                  <small>
                    {
                      phase14.secondRecognizerBenchmark.decision
                        .productionDecision
                    }
                  </small>
                </div>
              </div>
            )}
            {activePhase14Case && (
              <div className="phase14-review-grid">
              <div>
                <img
                  src={`${API_BASE}/phase14/crop?caseId=${encodeURIComponent(
                    activePhase14Case.caseId,
                  )}&profile=${encodeURIComponent(
                    phase14.selection.bestCropProfile,
                  )}`}
                  alt={`OCR crop ${phase14CaseIndex + 1}`}
                />
                <div className="draft-source-actions">
                  <button
                    onClick={() => selectPhase14Case(phase14CaseIndex - 1)}
                    disabled={phase14CaseIndex === 0}
                  >
                    ← Dòng trước
                  </button>
                  <span>
                    Còn {phase14CaseIndex + 1}/{phase14PendingCases.length}
                  </span>
                  <button
                    onClick={() => selectPhase14Case(phase14CaseIndex + 1)}
                    disabled={
                      phase14CaseIndex >= phase14PendingCases.length - 1
                    }
                  >
                    Dòng sau →
                  </button>
                </div>
              </div>
              <div>
                <div className="phase14-candidates">
                  <p>
                    <span>Paddle</span>
                    {
                      activePhase14Case.predictions.paddle_detector_raw?.text
                    }
                  </p>
                  <p>
                    <span>EasyOCR</span>
                    {
                      activePhase14Case.predictions[
                        phase14.selection.bestEasyProfile
                      ]?.text
                    }
                  </p>
                  <p>
                    <span>VietOCR</span>
                    {activePhase14Case.predictions.vietocr_best_crop?.text}
                  </p>
                </div>
                <label className="review-editor">
                  <span>Ground Truth dòng</span>
                  <textarea
                    value={phase14GroundTruth}
                    onChange={(event) =>
                      setPhase14GroundTruth(event.target.value)
                    }
                    spellCheck
                  />
                </label>
                <div className="review-assertions">
                  <label>
                    <input
                      type="checkbox"
                      checked={phase14Assertions.comparedWithCrop}
                      onChange={(event) =>
                        setPhase14Assertions((current) => ({
                          ...current,
                          comparedWithCrop: event.target.checked,
                        }))
                      }
                    />
                    Tôi đã đối chiếu trực tiếp với crop
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={phase14Assertions.allTextChecked}
                      onChange={(event) =>
                        setPhase14Assertions((current) => ({
                          ...current,
                          allTextChecked: event.target.checked,
                        }))
                      }
                    />
                    Tôi đã kiểm tra chữ và toàn bộ dấu tiếng Việt
                  </label>
                </div>
                <button
                  className="save-review"
                  onClick={savePhase14Review}
                  disabled={
                    isSavingPhase14 ||
                    !phase14GroundTruth.trim() ||
                    !phase14Assertions.comparedWithCrop ||
                    !phase14Assertions.allTextChecked
                  }
                >
                  {isSavingPhase14
                    ? "Đang lưu…"
                    : "Xác nhận dòng và chuyển tiếp"}
                </button>
              </div>
              </div>
            )}
            {!activePhase14Case && (
              <div className="phase14-complete">
                <strong>309/309 Ground Truth đã xác nhận</strong>
                <p>
                  Queue review đã hoàn tất. Prediction bịt kín đã được mở khóa
                  cho benchmark aggregate; không còn crop pending.
                </p>
              </div>
            )}
          </div>
        )}

        <div className="upload-layout">
          <div>
            <form onSubmit={submitUpload} className="upload-form">
              <div className="upload-mode-switch" role="tablist" aria-label="Chế độ xử lý">
                <button
                  aria-selected={processingMode === "template"}
                  className={processingMode === "template" ? "active" : ""}
                  onClick={() => {
                    setProcessingMode("template");
                    setUploadFile(null);
                    setUploadError("");
                    setLoadedUserResult(null);
                    setDeleteArmed(false);
                  }}
                  role="tab"
                  type="button"
                >
                  <strong>Mẫu chuẩn</strong>
                  <span>DOCX · không OCR</span>
                </button>
                <button
                  aria-selected={processingMode === "legacy"}
                  className={processingMode === "legacy" ? "active" : ""}
                  onClick={() => {
                    setProcessingMode("legacy");
                    setUploadFile(null);
                    setUploadError("");
                    setTemplateResult(null);
                    setDeleteArmed(false);
                  }}
                  role="tab"
                  type="button"
                >
                  <strong>OCR / IDP cũ</strong>
                  <span>Ảnh, PDF, Office</span>
                </button>
              </div>

              {processingMode === "template" && (
                <div className="template-registry">
                  <span>TEMPLATE-FIRST · CLOSED SET</span>
                  <p>
                    Hệ thống đọc trực tiếp DOCX và chỉ nhận hai biểu mẫu đã được
                    kiểm thử.
                  </p>
                  <div>
                    {supportedTemplates.map((template) => (
                      <small key={template.templateId}>
                        {template.templateId}
                      </small>
                    ))}
                  </div>
                </div>
              )}

              <label
                className={`drop-zone ${isDragging ? "dragging" : ""} ${
                  uploadFile ? "has-file" : ""
                }`}
                onDragEnter={(event) => {
                  event.preventDefault();
                  setIsDragging(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setIsDragging(false);
                  const file = event.dataTransfer.files[0];
                  if (file) setUploadFile(file);
                }}
              >
                <input
                  type="file"
                  data-testid="local-document-input"
                  accept={
                    processingMode === "template"
                      ? ".docx"
                      : ".png,.jpg,.jpeg,.pdf,.docx,.xlsx"
                  }
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
                <span className="upload-icon">＋</span>
                <strong>
                  {uploadFile ? uploadFile.name : "Kéo thả hoặc chọn tài liệu"}
                </strong>
                <p>
                  {uploadFile
                    ? `${(uploadFile.size / 1024 / 1024).toFixed(2)} MB`
                    : processingMode === "template"
                      ? "DOCX có text · đơn nghỉ phép hoặc đơn tăng ca"
                      : "PNG, JPG, JPEG, PDF, DOCX, XLSX, tối đa 50 MB / 50 trang"}
                </p>
              </label>
              <div className="upload-consent">
                <span>PII MODE</span>
                <p>
                  Bạn xác nhận có quyền sử dụng tài liệu. Session được giữ trong
                  private-data cho đến khi bạn bấm xóa.
                </p>
              </div>
              <button
                className="process-button"
                data-testid="process-document-button"
                disabled={!uploadFile || isUploading}
              >
                {isUploading
                  ? processingMode === "template"
                    ? "Đang đọc biểu mẫu local…"
                    : "Đang OCR local… có thể mất vài phút"
                  : processingMode === "template"
                    ? "Trích xuất theo mẫu chuẩn"
                    : "Phân tích bằng OCR / IDP"}
              </button>
              {uploadError && <div className="upload-error">{uploadError}</div>}
            </form>

            {processingMode === "legacy" && (
              <div className="session-history">
                <div>
                  <h3>Lịch sử upload private</h3>
                  <button
                    type="button"
                    onClick={() => setShowSessionHistory((current) => !current)}
                  >
                    {showSessionHistory
                      ? "Ẩn lịch sử"
                      : `Mở ${userSessions.length} session`}
                  </button>
                </div>
                {showSessionHistory && userSessions.length ? (
                  <ul>
                    {userSessions.slice(0, 20).map((session) => (
                      <li key={session.sessionId}>
                        <button onClick={() => loadUserSession(session.sessionId)}>
                          <span>
                            <strong>{session.originalFileName}</strong>
                            <small>
                              {session.format} / {session.pageCount} trang /{" "}
                              {session.recognizedTextLineCount} dòng
                              {session.reviewed ? " / Ground truth ✓" : ""}
                              {session.phase15Reviewed ? " / Field review ✓" : ""}
                            </small>
                          </span>
                          <b>{pct(session.avgConfidence)}</b>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : showSessionHistory ? (
                  <p>Chưa có tài liệu thật nào được lưu.</p>
                ) : null}
              </div>
            )}
          </div>

          <div className="upload-result">
            {!userResult && !templateResult && !isUploading && (
              <div className="result-placeholder">
                <span>JSON</span>
                <h3>Kết quả sẽ xuất hiện tại đây</h3>
                <p>
                  {processingMode === "template"
                    ? "Các trường trong biểu mẫu, dữ liệu thiếu, validation và JSON chuẩn sẽ hiển thị tại đây."
                    : "Bao gồm raw OCR text, confidence, bounding boxes, field candidates, visualization và processing metadata."}
                </p>
              </div>
            )}
            {isUploading && (
              <div className="result-placeholder processing">
                <i />
                <h3>
                  {processingMode === "template"
                    ? "Đang đọc trực tiếp nội dung DOCX"
                    : "Đang nạp model và đọc tài liệu"}
                </h3>
                <p>
                  {processingMode === "template"
                    ? "Không sử dụng OCR hoặc dịch vụ cloud."
                    : "Lần đầu có thể chậm hơn. Không đóng localhost trong khi xử lý."}
                </p>
              </div>
            )}
            {templateResult && (
              <TemplateResultPanel
                deleteArmed={deleteArmed}
                filename={uploadFile?.name ?? "Tài liệu DOCX"}
                onDelete={deleteTemplateSession}
                result={templateResult}
              />
            )}
            {userResult && (
              <div className="user-result-panel">
                <div className="user-result-head">
                  <div>
                    <p className="eyebrow">SESSION RESULT</p>
                    <h3>{userResult.source.originalFileName}</h3>
                    <span>
                      {userResult.source.format} / {userResult.source.pageCount} trang /{" "}
                      {userResult.document.recognizedTextLineCount} dòng
                    </span>
                  </div>
                  <span
                    className={`status-pill ${
                      userResult.document.ocrSuccess ? "success" : "failed"
                    }`}
                  >
                    {userResult.document.ocrSuccess ? "OCR success" : "No text"}
                  </span>
                </div>

                {userResult.phase9 && (
                  <div className="phase9-strip">
                    <div>
                      <span>DOCUMENT ROUTE</span>
                      <strong>{userResult.phase9.documentRoute.type}</strong>
                      <small>{pct(userResult.phase9.documentRoute.confidence)} confidence</small>
                    </div>
                    <div>
                      <span>SELECTED OCR</span>
                      <strong>
                        {userResult.phase9.selectedVariant === "phase9_routed"
                          ? "Routed preprocessing"
                          : "Phase 8 raw"}
                      </strong>
                      <small>
                        {userResult.phase9.pages[activeUserPage]?.readingOrderStrategy ??
                          "top_to_bottom"}
                      </small>
                    </div>
                    <div
                      className={`gate-${userResult.phase9.qualityGate.status.toLowerCase()}`}
                    >
                      <span>QUALITY GATE</span>
                      <strong>{userResult.phase9.qualityGate.status}</strong>
                      <small>
                        {userResult.phase9.qualityGate.lowConfidenceLineCount} dòng cần xem
                      </small>
                    </div>
                  </div>
                )}

                {userResult.phase11?.identityCard && (
                  <div className="phase11-strip">
                    <div>
                      <span>
                        PHASE {phase11Label(userResult)} / CCCD
                      </span>
                      <strong>{userResult.phase11.status}</strong>
                      <small>
                        Xoay{" "}
                        {userResult.phase11.orientation.pages[activeUserPage]
                          ?.selectedRotationDegrees ?? 0}
                        °
                      </small>
                    </div>
                    <div>
                      <span>PERSPECTIVE</span>
                      <strong>
                        {userResult.phase11.canonicalization?.[activeUserPage]
                          ?.perspectiveCorrected
                          ? "Đã chuẩn hóa"
                          : "Giữ ảnh định hướng"}
                      </strong>
                      <small>
                        {userResult.phase11.canonicalization?.[
                          activeUserPage
                        ]?.canonicalSize.join(" × ") ?? "Chưa có"}
                      </small>
                    </div>
                    <div>
                      <span>DOCUMENT COMPLETENESS</span>
                      <strong>
                        {pct(
                          userResult.phase11.identityCard.summary
                            .documentCompleteness,
                        )}
                      </strong>
                      <small>
                        {userResult.phase11.identityCard.summary.acceptedFieldCount}/
                        {userResult.phase11.identityCard.summary.expectedFieldCount} trường
                        accepted
                      </small>
                    </div>
                  </div>
                )}

                {userResult.phase14_8 && (
                  <div className="phase14-8-strip">
                    <div>
                      <span>PHASE 14.8 / PRIMARY</span>
                      <strong>
                        {userResult.phase14_8.status === "NOT_REQUIRED_NATIVE_INPUT"
                          ? "Native parser"
                          : "VietOCR Seq2Seq"}
                      </strong>
                      <small>
                        {userResult.phase14_8.status === "NOT_REQUIRED_NATIVE_INPUT"
                          ? "Không OCR lại tài liệu native"
                          : "Paddle chỉ cung cấp geometry"}
                      </small>
                    </div>
                    <div>
                      <span>TRANSFORMER VERIFIER</span>
                      <strong>{userResult.phase14_8.status}</strong>
                      <small>
                        {userResult.phase14_8.summary.verifiedLineCount}/
                        {userResult.phase14_8.summary.lineCount} dòng đồng thuận
                      </small>
                    </div>
                    <div>
                      <span>HUMAN REVIEW</span>
                      <strong>
                        {userResult.phase14_8.summary.needsReviewLineCount} dòng
                      </strong>
                      <small>
                        Không tự thay text khi hai recognizer bất đồng
                      </small>
                    </div>
                  </div>
                )}

                {unifiedIdp && (
                  <div className="phase12-strip">
                    <div>
                      <span>PHASE 15 / UNIFIED INTAKE</span>
                      <strong>
                        {unifiedIdp.ingestion.sourceFormat} /{" "}
                        {unifiedIdp.ingestion.mode}
                      </strong>
                      <small>{unifiedIdp.ingestion.adapter}</small>
                    </div>
                    <div>
                      <span>DOCUMENT FAMILY</span>
                      <strong>
                        {familyLabels[
                          unifiedIdp.classification.documentFamily ??
                            "OTHER_HR_DOCUMENT"
                        ] ??
                          unifiedIdp.classification.documentFamily ??
                          "Chưa xác định"}
                      </strong>
                      <small>1 trong 5 họ tài liệu HCNS</small>
                    </div>
                    <div>
                      <span>DOCUMENT SUBTYPE</span>
                      <strong>
                        {typeLabels[unifiedIdp.classification.documentType] ??
                          unifiedIdp.classification.documentType}
                      </strong>
                      <small>
                        {pct(unifiedIdp.classification.confidence)} confidence /{" "}
                        {unifiedIdp.classification.status}
                      </small>
                    </div>
                    <div>
                      <span>BUSINESS EXTRACTION</span>
                      <strong>{unifiedIdp.status}</strong>
                      <small>
                        {pct(
                          unifiedIdp.extraction.summary.documentCompleteness,
                        )}{" "}
                        completeness /{" "}
                        {unifiedIdp.extraction.summary.acceptedFieldCount}/
                        {unifiedIdp.extraction.summary.expectedFieldCount} accepted
                      </small>
                    </div>
                  </div>
                )}

                {unifiedIdp &&
                  Object.keys(unifiedIdp.extraction.fields).length > 0 && (
                    <section className="phase15-fields" aria-label="Trường dữ liệu HCNS">
                      <div className="phase15-fields-head">
                        <div>
                          <span>STRUCTURED BUSINESS FIELDS</span>
                          <h4>Thông tin trích xuất theo loại tài liệu</h4>
                        </div>
                        <small>
                          Trường thiếu hoặc chưa chắc chắn luôn cần người duyệt
                        </small>
                      </div>
                      <div className="phase15-field-grid">
                        {Object.entries(unifiedIdp.extraction.fields).map(
                          ([fieldName, field]) => (
                            <article
                              className={`phase15-field field-${field.status}`}
                              key={fieldName}
                            >
                              <div>
                                <span>
                                  {businessFieldLabels[fieldName] ?? fieldName}
                                </span>
                                {field.sensitive && <em>Nhạy cảm</em>}
                              </div>
                              {userResult.phase15 ? (
                                <textarea
                                  aria-label={`Review ${
                                    businessFieldLabels[fieldName] ?? fieldName
                                  }`}
                                  value={phase15FieldDraft[fieldName] ?? ""}
                                  placeholder="Chưa tìm thấy"
                                  onChange={(event) =>
                                    setPhase15FieldDraft((current) => ({
                                      ...current,
                                      [fieldName]: event.target.value,
                                    }))
                                  }
                                />
                              ) : (
                                <strong>
                                  {field.value === null || field.value === ""
                                    ? "Chưa tìm thấy"
                                    : String(field.normalizedValue ?? field.value)}
                                </strong>
                              )}
                              <small>
                                {field.status} / {pct(field.confidence)}
                              </small>
                            </article>
                          ),
                        )}
                      </div>
                      {unifiedIdp.extraction.tables.length > 0 && (
                        <div className="phase15-table-summary">
                          <strong>
                            {unifiedIdp.extraction.tables.length} bảng dữ liệu
                          </strong>
                          <span>
                            {unifiedIdp.extraction.tables.reduce(
                              (total, table) => total + table.summary.rowCount,
                              0,
                            )}{" "}
                            dòng được giữ cùng provenance
                          </span>
                        </div>
                      )}
                      {userResult.phase15 && (
                        <div className="phase15-review">
                          <div className="phase15-review-checks">
                            <label>
                              <input
                                type="checkbox"
                                checked={phase15ReviewAssertions.comparedWithSource}
                                onChange={(event) =>
                                  setPhase15ReviewAssertions((current) => ({
                                    ...current,
                                    comparedWithSource: event.target.checked,
                                  }))
                                }
                              />
                              Tôi đã đối chiếu từng trường với tài liệu gốc
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                checked={phase15ReviewAssertions.allFieldsChecked}
                                onChange={(event) =>
                                  setPhase15ReviewAssertions((current) => ({
                                    ...current,
                                    allFieldsChecked: event.target.checked,
                                  }))
                                }
                              />
                              Tôi đã kiểm tra cả trường trống và dấu tiếng Việt
                            </label>
                          </div>
                          <button
                            type="button"
                            onClick={savePhase15Review}
                            disabled={
                              isSavingPhase15Review ||
                              !phase15ReviewAssertions.comparedWithSource ||
                              !phase15ReviewAssertions.allFieldsChecked
                            }
                          >
                            {isSavingPhase15Review
                              ? "Đang lưu review local…"
                              : userResult.phase15.review
                                ? "Cập nhật review Phase 15"
                                : "Xác nhận các trường Phase 15"}
                          </button>
                          {userResult.phase15.review && (
                            <small>
                              USER_REVIEWED ·{" "}
                              {userResult.phase15.review.correctedFieldCount} trường đã
                              sửa · artifact tự động vẫn được giữ nguyên
                            </small>
                          )}
                        </div>
                      )}
                    </section>
                  )}

                <div className="user-result-metrics">
                  <div>
                    <span>Confidence</span>
                    <strong>{pct(userResult.document.avgConfidence)}</strong>
                  </div>
                  <div>
                    <span>Inference</span>
                    <strong>{duration(userResult.processing.inferenceDurationMs)}</strong>
                  </div>
                  <div>
                    <span>Total</span>
                    <strong>{duration(userResult.processing.totalDurationMs)}</strong>
                  </div>
                  <div>
                    <span>PII</span>
                    <strong>{userResult.containsRealPII ? "Private" : "No"}</strong>
                  </div>
                </div>

                <div className="result-actions">
                  <a
                    href={`${API_BASE}/user/download?id=${encodeURIComponent(
                      userResult.sessionId,
                    )}`}
                    download
                  >
                    Tải Native JSON
                  </a>
                  {userResult.phase11?.identityCard && (
                    <a
                      className="secondary-download"
                      href={`${API_BASE}/user/identity-card?id=${encodeURIComponent(
                        userResult.sessionId,
                      )}`}
                      download
                    >
                      Tải CCCD JSON
                    </a>
                  )}
                  {userResult.phase14_8?.download && (
                    <a
                      className="secondary-download"
                      href={`${API_BASE}/user/phase14-8-recognition?id=${encodeURIComponent(
                        userResult.sessionId,
                      )}`}
                      download
                    >
                      Tải Recognition JSON
                    </a>
                  )}
                  {userResult.phase11_3 && (
                    <a
                      className="secondary-download"
                      href={`${API_BASE}/user/phase11-3-evidence?id=${encodeURIComponent(
                        userResult.sessionId,
                      )}`}
                      download
                    >
                      Tải Phase 11.3 JSON
                    </a>
                  )}
                  {userResult.phase11_4 && (
                    <a
                      className="secondary-download"
                      href={`${API_BASE}/user/phase11-4-evidence?id=${encodeURIComponent(
                        userResult.sessionId,
                      )}`}
                      download
                    >
                      Tải Phase 11.4 JSON
                    </a>
                  )}
                  {userResult.phase11_5 && (
                    <a
                      className="secondary-download"
                      href={`${API_BASE}/user/phase11-5-evidence?id=${encodeURIComponent(
                        userResult.sessionId,
                      )}`}
                      download
                    >
                      Táº£i Phase 11.5 JSON
                    </a>
                  )}
                  {unifiedIdp && (
                    <>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/${
                          userResult.phase15 ? "phase15" : "phase12"
                        }-canonical?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải Canonical JSON
                      </a>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/${
                          userResult.phase15 ? "phase15" : "phase12"
                        }-result?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải IDP JSON
                      </a>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/${
                          userResult.phase15 ? "phase15" : "phase12"
                        }-business?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải Business JSON
                      </a>
                    </>
                  )}
                  {userResult.phase15?.review && (
                    <>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/phase15-reviewed-result?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải IDP đã duyệt
                      </a>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/phase15-reviewed-business?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải Business đã duyệt
                      </a>
                    </>
                  )}
                  <button className="phase9-button" onClick={reprocessPhase9}>
                    {isReprocessing
                      ? "Đang chạy Phase 9 + 11 nền…"
                      : "Chạy lại Phase 9 + 11 nền"}
                  </button>
                  <button
                    className={deleteArmed ? "armed" : ""}
                    onClick={deleteUserSession}
                  >
                    {deleteArmed
                      ? "Bấm lần nữa để xóa vĩnh viễn"
                      : "Xóa session"}
                  </button>
                </div>

                {userResult.phase9?.qualityGate.warnings.length ? (
                  <div className="quality-warnings">
                    <strong>Cần kiểm tra thủ công</strong>
                    <ul>
                      {userResult.phase9.qualityGate.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {userResult.phase11?.identityCard && (
                  <div className="identity-fields">
                    <div className="identity-fields-title">
                      <div>
                        <span>STRUCTURED CCCD JSON</span>
                        <h4>Trường có bằng chứng OCR</h4>
                      </div>
                      <b
                        className={
                          userResult.phase11.identityCard.summary
                            .readyForAutomaticUse
                            ? "accepted"
                            : "needs_review"
                        }
                      >
                        {userResult.phase11.identityCard.summary
                          .readyForAutomaticUse
                          ? "READY"
                          : "NEEDS REVIEW"}
                      </b>
                    </div>
                    <div className="identity-field-grid">
                      {Object.entries(
                        userResult.phase11.identityCard.fields,
                      ).map(([field, item]) => (
                        <div className={`identity-field ${item.status}`} key={field}>
                          <span>{identityFieldLabels[field] ?? field}</span>
                          <strong>{item.value ?? "Không tìm thấy"}</strong>
                          <small>
                            {item.status} / {pct(item.confidence)}
                            {item.evidence
                              ? ` / dòng ${item.evidence.lineIndices
                                  .map((index) => index + 1)
                                  .join(", ")}`
                              : ""}
                          </small>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="candidate-fields">
                  <h4>Thông tin phát hiện</h4>
                  {Object.entries(userResult.document.extractedCandidates).map(
                    ([field, values]) => (
                      <div key={field}>
                        <span>{field}</span>
                        <p>{values.length ? values.join(", ") : "Không phát hiện"}</p>
                      </div>
                    ),
                  )}
                </div>

                {userResult.document.pages.length > 1 && (
                  <div className="page-tabs">
                    {userResult.document.pages.map((page) => (
                      <button
                        key={page.pageIndex}
                        className={activeUserPage === page.pageIndex ? "active" : ""}
                        onClick={() => setActiveUserPage(page.pageIndex)}
                      >
                        Trang {page.pageIndex + 1}
                      </button>
                    ))}
                  </div>
                )}

                {(userResult.phase11?.pages?.[activeUserPage]?.lines.length ||
                  userResult.document.pages[activeUserPage]
                    ?.visualizationAvailable) && (
                  <div className="user-visualization">
                    <img
                      src={`${API_BASE}/user/visualization?id=${encodeURIComponent(
                        userResult.sessionId,
                      )}&page=${activeUserPage}`}
                      alt={`OCR visualization trang ${activeUserPage + 1}`}
                    />
                  </div>
                )}

                <div className="user-ocr-output">
                  <div>
                    <div>
                      <h4>Recognized text</h4>
                      <span>Trang {activeUserPage + 1}</span>
                    </div>
                    {userResult.phase9 && (
                      <div className="text-toggle">
                        <button
                          className={textView === "corrected" ? "active" : ""}
                          onClick={() => setTextView("corrected")}
                        >
                          Corrected
                        </button>
                        <button
                          className={textView === "raw" ? "active" : ""}
                          onClick={() => setTextView("raw")}
                        >
                          Raw OCR
                        </button>
                      </div>
                    )}
                  </div>
                  <ol>
                    {(userResult.phase11?.pages?.[activeUserPage]?.lines ??
                      userResult.phase9?.pages[activeUserPage]?.lines ??
                      userResult.document.pages[activeUserPage]?.recognizedTexts.map(
                        (text, index) => ({
                          sourceIndex: index,
                          outputIndex: index,
                          rawText: text,
                          correctedText: text,
                          confidence:
                            userResult.document.pages[activeUserPage].recognitionScores[
                              index
                            ] ?? null,
                          correctionApplied: false,
                          correctionMethod: null,
                          warning: null,
                        }),
                      ) ??
                      []
                    ).map((line) => (
                      <li
                        className={`${line.warning ? "low-confidence" : ""} ${
                          line.correctionApplied && textView === "corrected"
                            ? "corrected"
                            : ""
                        }`}
                        key={`${line.sourceIndex}-${line.outputIndex}`}
                      >
                        <span>{line.outputIndex + 1}</span>
                        <p>
                          {textView === "corrected"
                            ? line.correctedText
                            : line.rawText}
                          {line.correctionApplied && textView === "corrected" && (
                            <em>restored</em>
                          )}
                        </p>
                        <small>{pct(line.confidence)}</small>
                      </li>
                    ))}
                  </ol>
                </div>

                {phase10Review && (
                  <div className="phase10-review">
                    <div className="phase10-title">
                      <div>
                        <p className="eyebrow">PHASE 14.2 / CONTROLLED OCR PILOT</p>
                        <h4>Paddle detector → VietOCR primary → Paddle verifier</h4>
                      </div>
                      <span
                        className={
                          phase10Review.hybrid.available ? "verified" : "draft"
                        }
                      >
                        {phase10Review.hybrid.available
                          ? "EVIDENCE READY"
                          : "NOT RUN"}
                      </span>
                    </div>
                    <p className="review-help">
                      VietOCR giữ candidate chính. Chỉ dòng khớp hoàn toàn với Paddle
                      mới được chấp nhận; mọi bất đồng giữ candidate VietOCR nhưng mang
                      trạng thái needs_review. Confidence không thể tự động duyệt.
                    </p>
                    {phase10Review.hybrid.available ? (
                      <>
                        <div className="evaluation-grid">
                          <div>
                            <span>Detected crops</span>
                            <strong>
                              {phase10Review.hybrid.summary?.cropCount ?? 0}
                            </strong>
                          </div>
                          <div>
                            <span>Accepted</span>
                            <strong>
                              {phase10Review.hybrid.summary?.acceptedLineCount ?? 0}
                            </strong>
                            <small>
                              {pct(
                                phase10Review.hybrid.summary?.acceptanceRate ?? null,
                              )}
                            </small>
                          </div>
                          <div>
                            <span>Needs review</span>
                            <strong>
                              {phase10Review.hybrid.summary?.needsReviewLineCount ?? 0}
                            </strong>
                          </div>
                        </div>
                        <div className="draft-source-actions">
                          <button
                            onClick={runHybridOcr}
                            disabled={isRunningHybrid}
                          >
                            {isRunningHybrid
                              ? "Đang chạy lại controlled pilot…"
                              : "Chạy lại Phase 14.2"}
                          </button>
                          <a
                            href={`${API_BASE}/user/phase14-2-result?id=${encodeURIComponent(
                              userResult.sessionId,
                            )}`}
                          >
                            Tải JSON bằng chứng
                          </a>
                        </div>
                      </>
                    ) : (
                      <div className="draft-source-actions">
                        <button
                          className="challenger-ready"
                          onClick={runHybridOcr}
                          disabled={isRunningHybrid}
                        >
                          {isRunningHybrid
                            ? "Đang chạy Paddle → VietOCR → Paddle verifier…"
                            : "Chạy Phase 14.2 controlled pilot"}
                        </button>
                      </div>
                    )}

                    <div className="phase10-title">
                      <div>
                        <p className="eyebrow">PHASE 10 / USER-REVIEWED GROUND TRUTH</p>
                        <h4>
                          {phase10Review.reviewed
                            ? "Ground truth đã được xác nhận"
                            : "Xác nhận nội dung đúng"}
                        </h4>
                      </div>
                      <span className={phase10Review.reviewed ? "verified" : "draft"}>
                        {phase10Review.reviewed
                          ? "USER REVIEWED"
                          : phase10Review.reviewStatus === "NEEDS_RECONFIRMATION"
                            ? "RECONFIRM"
                            : "DRAFT"}
                      </span>
                    </div>
                    <p className="review-help">
                      Đây chỉ là bản nháp OCR, chưa phải Ground Truth. Hãy đối chiếu trực
                      tiếp với ảnh, sửa cả chữ bị mất và dấu tiếng Việt trước khi xác nhận.
                    </p>
                    <div className="draft-source-actions">
                      <button
                        onClick={() => {
                          setReviewDraft(
                            phase10Review.draftPages.map((page) => ({ ...page })),
                          );
                          setReviewAssertions({
                            comparedWithImage: false,
                            allTextChecked: false,
                            acceptUnchangedDraft: false,
                          });
                        }}
                      >
                        Dùng bản Phase 9
                      </button>
                      {phase10Review.challenger.available &&
                      phase10Review.challenger.draftPages ? (
                        <button
                          className="challenger-ready"
                          onClick={() => {
                            setReviewDraft(
                              phase10Review.challenger.draftPages!.map((page) => ({
                                ...page,
                              })),
                            );
                            setReviewAssertions({
                              comparedWithImage: false,
                              allTextChecked: false,
                              acceptUnchangedDraft: false,
                            });
                          }}
                        >
                          Dùng EasyOCR vi /{" "}
                          {pct(phase10Review.challenger.avgConfidence ?? null)}
                        </button>
                      ) : (
                        <button
                          className="challenger-ready"
                          onClick={runEasyOcrChallenger}
                          disabled={isRunningChallenger}
                        >
                          {isRunningChallenger
                            ? "Đang chạy EasyOCR vi…"
                            : "Tạo gợi ý EasyOCR vi"}
                        </button>
                      )}
                    </div>
                    <label className="review-editor">
                      <span>Ground truth / Trang {activeUserPage + 1}</span>
                      <textarea
                        value={reviewDraft[activeUserPage]?.text ?? ""}
                        onChange={(event) =>
                          setReviewDraft((current) =>
                            current.map((page) =>
                              page.pageIndex === activeUserPage
                                ? { ...page, text: event.target.value }
                                : page,
                            ),
                          )
                        }
                        spellCheck
                      />
                    </label>
                    {userResult.phase11?.identityCard && (
                      <div className="identity-ground-truth">
                        <div>
                          <strong>Ground Truth theo trường CCCD</strong>
                          <span>
                            Đối chiếu từng giá trị với ảnh; để trống nếu trường không
                            xuất hiện.
                          </span>
                        </div>
                        <div className="identity-ground-truth-grid">
                          {Object.keys(identityFieldLabels).map((field) => (
                            <label key={field}>
                              <span>{identityFieldLabels[field]}</span>
                              <input
                                value={identityFieldDraft[field] ?? ""}
                                onChange={(event) =>
                                  setIdentityFieldDraft((current) => ({
                                    ...current,
                                    [field]: event.target.value,
                                  }))
                                }
                                spellCheck
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="review-assertions">
                      <label>
                        <input
                          type="checkbox"
                          checked={reviewAssertions.comparedWithImage}
                          onChange={(event) =>
                            setReviewAssertions((current) => ({
                              ...current,
                              comparedWithImage: event.target.checked,
                            }))
                          }
                        />
                        Tôi đã đối chiếu trực tiếp với ảnh gốc
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={reviewAssertions.allTextChecked}
                          onChange={(event) =>
                            setReviewAssertions((current) => ({
                              ...current,
                              allTextChecked: event.target.checked,
                            }))
                          }
                        />
                        Tôi đã kiểm tra đủ chữ, dấu, số và các dòng bị bỏ sót
                      </label>
                      {reviewDraftIsUnchanged && (
                        <label className="unchanged-warning">
                          <input
                            type="checkbox"
                            checked={reviewAssertions.acceptUnchangedDraft}
                            onChange={(event) =>
                              setReviewAssertions((current) => ({
                                ...current,
                                acceptUnchangedDraft: event.target.checked,
                              }))
                            }
                          />
                          Bản OCR draft đã đúng hoàn toàn, tôi xác nhận không cần sửa
                        </label>
                      )}
                    </div>
                    <button
                      className="save-review"
                      onClick={savePhase10Review}
                      disabled={
                        isSavingReview ||
                        !reviewDraft.length ||
                        !reviewAssertions.comparedWithImage ||
                        !reviewAssertions.allTextChecked ||
                        (reviewDraftIsUnchanged &&
                          !reviewAssertions.acceptUnchangedDraft)
                      }
                    >
                      {isSavingReview
                        ? "Đang đánh giá…"
                        : phase10Review.reviewed
                          ? "Cập nhật ground truth"
                          : "Xác nhận và tính CER/WER"}
                    </button>

                    {phase10Review.evaluation && (
                      <>
                        <div className="evaluation-grid">
                          {(
                            [
                              ["phase8Raw", "Phase 8 Raw"],
                              ["phase9Selected", "Phase 9 Selected"],
                              ["phase9Corrected", "Phase 9 Corrected"],
                              ["easyocrChallenger", "EasyOCR vi"],
                            ] as const
                          ).map(([key, label]) => {
                            const metric = phase10Review.evaluation!.aggregate[key];
                            if (!metric) return null;
                            return (
                              <div key={key}>
                                <span>{label}</span>
                                <strong>CER {decimal(metric.cer)}</strong>
                                <small>
                                  WER {decimal(metric.wer)} /{" "}
                                  {metric.exactMatch ? "Exact" : "Not exact"}
                                </small>
                              </div>
                            );
                          })}
                        </div>
                        {phase10Review.evaluation.fieldEvaluation && (
                          <div className="field-evaluation">
                            <div>
                              <span>PHASE 9 BEFORE</span>
                              <strong>
                                {pct(
                                  phase10Review.evaluation.fieldEvaluation.variants
                                    .phase9Before?.fieldExactMatch ?? null,
                                )}
                              </strong>
                              <small>
                                Completeness{" "}
                                {pct(
                                  phase10Review.evaluation.fieldEvaluation.variants
                                    .phase9Before?.documentCompleteness ?? null,
                                )}
                              </small>
                            </div>
                            <div>
                              <span>
                                PHASE {phase11Label(userResult)} AFTER
                              </span>
                              <strong>
                                {pct(
                                  phase10Review.evaluation.fieldEvaluation.variants
                                    .phase11After?.fieldExactMatch ?? null,
                                )}
                              </strong>
                              <small>
                                Completeness{" "}
                                {pct(
                                  phase10Review.evaluation.fieldEvaluation.variants
                                    .phase11After?.documentCompleteness ?? null,
                                )}
                              </small>
                            </div>
                          </div>
                        )}
                        <div className="phase10-downloads">
                          <a
                            href={`${API_BASE}/user/ground-truth?id=${encodeURIComponent(
                              userResult.sessionId,
                            )}`}
                          >
                            Ground Truth JSON
                          </a>
                          <a
                            href={`${API_BASE}/user/evaluation?id=${encodeURIComponent(
                              userResult.sessionId,
                            )}`}
                          >
                            Evaluation JSON
                          </a>
                          <a
                            href={`${API_BASE}/user/business?id=${encodeURIComponent(
                              userResult.sessionId,
                            )}`}
                          >
                            Business JSON pilot
                          </a>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="section" id="phases">
        <div className="section-heading">
          <div>
            <p className="eyebrow">LOCKED RECOGNITION POLICY</p>
            <h2>Phương pháp nào đang thực sự chạy?</h2>
          </div>
          <p>
            Pipeline scan hiện dùng policy đã khóa; “tối ưu” ở đây là cấu hình
            tốt nhất trong tập ứng viên, chưa đồng nghĩa đạt chất lượng production.
          </p>
        </div>
        <div className="phase-grid">
          <article className="phase-card">
            <div className="phase-top">
              <span>01</span>
              <b>Geometry only</b>
            </div>
            <h3>Paddle detector</h3>
            <p>
              PP-OCRv5 tìm vùng chữ và giữ bounding box làm bằng chứng. Text do
              Paddle nhận dạng không còn đủ điều kiện tự động được chọn.
            </p>
            <small>selectionEligible=false</small>
          </article>
          <article className="phase-card">
            <div className="phase-top">
              <span>02</span>
              <b>Primary active</b>
            </div>
            <h3>VietOCR vgg_seq2seq</h3>
            <p>
              Mỗi crop được nhận dạng lại bằng model có weight và SHA-256 đã
              khóa. Kết quả này là primary đưa vào Canonical Document của scan.
            </p>
            <small>primaryProfile=vietocr_vgg_seq2seq</small>
          </article>
          <article className="phase-card">
            <div className="phase-top">
              <span>03</span>
              <b>Verifier active</b>
            </div>
            <h3>VietOCR vgg_transformer</h3>
            <p>
              Transformer đọc cùng crop. Exact agreement được ghi nhận; bất đồng
              giữ nguyên primary và bắt buộc human review.
            </p>
            <small>disagreementAction=preserve_primary_and_require_review</small>
          </article>
          <article className="phase-card">
            <div className="phase-top">
              <span>04</span>
              <b>Safety lock</b>
            </div>
            <h3>Không auto-switch fallback</h3>
            <p>
              LODO từng tăng tổng Exact Match nhưng làm hỏng dòng primary vốn
              đúng. Vì vậy automatic replacement vẫn tắt.
            </p>
            <small>
              mode=SHADOW_REVIEW_ONLY · autoReplaceSelectedText=false
            </small>
          </article>
        </div>
      </section>

      {SHOW_HELDOUT ? (
        <section className="section metrics-section" id="metrics">
        <div className="section-heading">
          <div>
            <p className="eyebrow">REAL HELD-OUT · EVALUATE ONCE</p>
            <h2>Kết quả trên 18 tài liệu thật</h2>
          </div>
          <p>
            Chỉ hiển thị tập đã xác nhận Ground Truth và có quyền xử lý local.
            Không còn trộn số liệu Phase đầu, ảnh che PII hoặc synthetic vào đây.
          </p>
        </div>
        {heldoutError && <div className="api-warning">{heldoutError}</div>}
        <div className="metric-grid">
          <article className="metric-card accent">
            <span>CLASSIFICATION ↑</span>
            <strong>
              {pct(heldout?.overall.classificationAccuracy ?? null)}
            </strong>
            <p>Đúng nhóm tài liệu</p>
            <small>{heldout?.documentCount ?? 0} tài liệu / 5 nhóm HCNS</small>
          </article>
          <article className="metric-card">
            <span>FIELD EXACT ↑</span>
            <strong>
              {pct(heldout?.overall.fieldExactMatchRate ?? null)}
            </strong>
            <p>Giá trị trường khớp tuyệt đối</p>
            <small>
              {heldout?.overall.fieldExactMatchCount ?? 0}/
              {heldout?.overall.evaluatedFieldCount ?? 0} field
            </small>
          </article>
          <article className="metric-card">
            <span>COMPLETENESS ↑</span>
            <strong>{pct(heldout?.overall.fieldCompleteness ?? null)}</strong>
            <p>Trường có giá trị được trích xuất</p>
            <small>
              Accepted {pct(heldout?.overall.acceptedFieldRate ?? null)}
            </small>
          </article>
          <article className="metric-card">
            <span>CER / WER ↓</span>
            <strong>{pct(heldout?.overall.cer ?? null, 2)}</strong>
            <p>WER {pct(heldout?.overall.wer ?? null, 2)}</p>
            <small>DER {pct(heldout?.overall.der ?? null, 2)}</small>
          </article>
          <article className="metric-card dark">
            <span>PRODUCTION DECISION</span>
            <strong>
              {heldout?.decision.production === "NOT_PRODUCTION_READY"
                ? "Chưa sẵn sàng"
                : heldout?.decision.production ?? "Chưa có"}
            </strong>
            <p>{heldout?.decision.controlledPilot ?? "Chưa đánh giá"}</p>
            <small>
              {heldout?.decision.production ?? "Prediction ẩn · không retune"}
            </small>
          </article>
        </div>
        {replayAudit ? (
          <div className="latest-replay-panel">
            <header>
              <div>
                <span>
                  {replayIsLiveV5
                    ? "LIVE PP-OCRV5 REPLAY · AUDIT ONLY"
                    : "LOCKED V4 REPLAY · AUDIT ONLY"}
                </span>
                <strong>
                  {replayAudit.visualDocumentCount ??
                    replayAudit.visualDocumentsReOcred ??
                    0}{" "}
                  tài liệu OCR
                  {" · "}
                  {replayAudit.nativeDocumentCount ??
                    replayAudit.nativeDocumentsReparsed ??
                    0}{" "}
                  tài liệu native
                </strong>
              </div>
              <small>
                {replayIsLiveV5
                  ? "Đúng pipeline localhost mới nhất; Ground Truth đã tồn tại nên chỉ dùng để audit."
                  : "Ground Truth đã tồn tại trước replay — không đủ điều kiện promotion."}
              </small>
            </header>
            <div>
              <article>
                <span>Classification</span>
                <strong>
                  {pct(replayAudit.baseline.overall.classificationAccuracy)} →{" "}
                  {pct(replayAudit.latest.overall.classificationAccuracy)}
                </strong>
                <small>
                  {signedPoints(replayAudit.delta.classificationAccuracy)}
                </small>
              </article>
              <article>
                <span>Field Exact</span>
                <strong>
                  {pct(
                    replayAudit.baseline.overall.fieldExactMatchRate,
                  )}{" "}
                  →{" "}
                  {pct(
                    replayAudit.latest.overall.fieldExactMatchRate,
                  )}
                </strong>
                <small>
                  {signedPoints(
                    replayAudit.delta.fieldExactMatchRate,
                  )}
                </small>
              </article>
              <article>
                <span>Completeness</span>
                <strong>
                  {pct(
                    replayAudit.baseline.overall.fieldCompleteness,
                  )}{" "}
                  →{" "}
                  {pct(
                    replayAudit.latest.overall.fieldCompleteness,
                  )}
                </strong>
                <small>
                  {signedPoints(
                    replayAudit.delta.fieldCompleteness,
                  )}
                </small>
              </article>
              <article>
                <span>CER ↓</span>
                <strong>
                  {pct(replayAudit.baseline.overall.cer, 2)} →{" "}
                  {pct(replayAudit.latest.overall.cer, 2)}
                </strong>
                <small>{signedPoints(replayAudit.delta.cer)}</small>
              </article>
              <article>
                <span>Sensitive false acceptance</span>
                <strong>
                  {
                    replayAudit.baseline
                      .sensitiveFieldFalseAcceptanceCount
                  }{" "}
                  →{" "}
                  {
                    replayAudit.latest
                      .sensitiveFieldFalseAcceptanceCount
                  }
                </strong>
                <small>{replayAudit.decision.status}</small>
              </article>
            </div>
          </div>
        ) : null}
        <div className="performance-panel">
          <div className="panel-title">
            <div>
              <h3>Kết quả theo nhóm tài liệu thật</h3>
              <p>Field Exact Match và completeness</p>
            </div>
            <span>{heldout?.datasetId ?? "Real held-out chưa kết nối"}</span>
          </div>
          <div className="bars">
            {Object.entries(heldout?.byFamily ?? {}).map(([name, metric]) => (
              <div className="bar-row" key={name}>
                <span>{familyLabels[name] ?? name}</span>
                <div className="bar-track">
                  <i
                    style={{
                      width: `${Math.max(metric.fieldExactMatchRate * 100, 1)}%`,
                    }}
                  />
                </div>
                <b>{pct(metric.fieldExactMatchRate)}</b>
              </div>
            ))}
          </div>
          <aside>
            <span>TABLE CONTRACT</span>
            <strong>
              {heldout?.overall.exactTableCellCount ?? 0}/
              {heldout?.overall.expectedTableCellCount ?? 0} ô exact
            </strong>
            <b>
              Completeness {pct(heldout?.overall.tableCompleteness ?? null)}
            </b>
            <hr />
            <span>ĐÁNH GIÁ</span>
            <strong>{heldout?.evaluationRunCount ?? 0} lần duy nhất</strong>
            <b>
              {heldout?.thresholdRetuned ? "Có retune" : "Không retune held-out"}
            </b>
          </aside>
        </div>
        </section>
      ) : null}

      <section className="section explorer-section" id="explorer">
        <div className="section-heading">
          <div>
            <p className="eyebrow">LOCAL REAL-DOCUMENT EVIDENCE</p>
            <h2>Biểu mẫu HCNS chuẩn và CCCD</h2>
          </div>
          <p>
            Chỉ hiển thị đơn nghỉ phép, tăng ca theo template registry và CCCD
            đã review. Các upload HCNS generic cũ vẫn được giữ local.
          </p>
        </div>
        <div className="evidence-switch" role="tablist">
          {SHOW_HELDOUT ? (
            <button
              className={evidenceMode === "heldout" ? "active" : ""}
              onClick={() => setEvidenceMode("heldout")}
              role="tab"
              aria-selected={evidenceMode === "heldout"}
            >
              18 tài liệu HCNS held-out
            </button>
          ) : null}
          <button
            className={evidenceMode === "templates" ? "active" : ""}
            onClick={() => setEvidenceMode("templates")}
            role="tab"
            aria-selected={evidenceMode === "templates"}
          >
            {templateSessions.length} đơn nghỉ phép &amp; tăng ca
          </button>
          <button
            className={evidenceMode === "cccd" ? "active" : ""}
            onClick={() => setEvidenceMode("cccd")}
            role="tab"
            aria-selected={evidenceMode === "cccd"}
          >
            {reviewedCccdSessions.length} CCCD đã Ground Truth
          </button>
        </div>
        {SHOW_HELDOUT && evidenceMode === "heldout" ? (
          <div className="heldout-evidence-grid">
            <div className="heldout-document-list" role="list">
              {(heldout?.documents ?? []).map((document) => (
                <button
                  className={
                    document.documentId === activeHeldoutId ? "active" : ""
                  }
                  key={document.documentId}
                  onClick={() => setActiveHeldoutId(document.documentId)}
                  role="listitem"
                >
                  <span>{document.documentId}</span>
                  <strong>
                    {familyLabels[document.documentFamily] ??
                      document.documentFamily}
                  </strong>
                  <small>
                    {document.sourceFormat} ·{" "}
                    {document.previewAvailable ? "có preview" : "mở file gốc"}
                  </small>
                </button>
              ))}
            </div>
            <div className="heldout-preview">
              {activeHeldoutDocument?.previewAvailable ? (
                activeHeldoutDocument.sourceFormat === "PDF" ? (
                  <iframe
                    title={`Preview ${activeHeldoutDocument.documentId}`}
                    src={`${API_BASE}/heldout/document?id=${encodeURIComponent(
                      activeHeldoutDocument.documentId,
                    )}&mode=preview`}
                  />
                ) : (
                  <img
                    src={`${API_BASE}/heldout/document?id=${encodeURIComponent(
                      activeHeldoutDocument.documentId,
                    )}&mode=preview`}
                    alt={`Tài liệu thật ${activeHeldoutDocument.documentId}`}
                  />
                )
              ) : (
                <div className="native-heldout-file">
                  <span>{activeHeldoutDocument?.sourceFormat ?? "—"}</span>
                  <strong>Đối chiếu bằng ứng dụng local</strong>
                  <p>
                    DOCX/XLSX được đọc native nên không chuyển thành ảnh giả để
                    trình bày.
                  </p>
                </div>
              )}
              {activeHeldoutDocument && (
                <div className="heldout-preview-actions">
                  <div>
                    <strong>{activeHeldoutDocument.documentId}</strong>
                    <span>
                      {familyLabels[activeHeldoutDocument.documentFamily] ??
                        activeHeldoutDocument.documentFamily}
                    </span>
                  </div>
                  <a
                    href={`${API_BASE}/heldout/document?id=${encodeURIComponent(
                      activeHeldoutDocument.documentId,
                    )}&mode=source`}
                  >
                    Mở / tải file gốc
                  </a>
                </div>
              )}
            </div>
            <EvidenceInspector
              detail={heldoutEvidence}
              loading={heldoutEvidenceLoading}
              error={heldoutEvidenceError}
              view={evidenceInspectorView}
              onViewChange={setEvidenceInspectorView}
            />
          </div>
        ) : evidenceMode === "templates" ? (
          <div className="heldout-evidence-grid">
            <div className="heldout-document-list" role="list">
              {templateSessions.map((session, index) => (
                <button
                  className={
                    session.documentId === activeTemplateSession?.documentId
                      ? "active"
                      : ""
                  }
                  key={session.documentId}
                  onClick={() =>
                    setActiveTemplateSessionId(session.documentId)
                  }
                  role="listitem"
                >
                  <span>
                    {session.documentType === "LEAVE_REQUEST"
                      ? "NGHỈ PHÉP"
                      : "TĂNG CA"}
                    -{String(index + 1).padStart(2, "0")}
                  </span>
                  <strong>{session.originalFileName}</strong>
                  <small>
                    {session.templateId} · {session.recommendedAction} ·{" "}
                    {pct(session.confidence)}
                  </small>
                </button>
              ))}
            </div>
            <div className="heldout-preview">
              {activeTemplateSession ? (
                <div className="native-heldout-file template-native-preview">
                  <span>DOCX</span>
                  <strong>{activeTemplateSession.originalFileName}</strong>
                  <p>
                    {activeTemplateSession.documentType === "LEAVE_REQUEST"
                      ? "Đơn xin nghỉ phép"
                      : "Đơn xin tăng ca"}
                    . Dữ liệu được đọc trực tiếp từ OOXML, không dùng OCR.
                  </p>
                </div>
              ) : (
                <div className="native-heldout-file">
                  <strong>Chưa có đơn theo mẫu chuẩn</strong>
                  <p>
                    Upload đơn nghỉ phép hoặc tăng ca ở khu vực Mẫu chuẩn để xem
                    metadata và JSON tại đây.
                  </p>
                </div>
              )}
              {activeTemplateSession && (
                <div className="heldout-preview-actions">
                  <div>
                    <strong>{activeTemplateSession.originalFileName}</strong>
                    <span>
                      {activeTemplateSession.templateId} / phiên bản{" "}
                      {activeTemplateSession.templateVersion} · confidence{" "}
                      {pct(activeTemplateSession.confidence)}
                    </span>
                  </div>
                </div>
              )}
            </div>
            <TemplateEvidenceInspector
              result={templateEvidenceResult}
              loading={templateEvidenceLoading}
              error={templateEvidenceError}
              view={evidenceInspectorView}
              onViewChange={setEvidenceInspectorView}
            />
          </div>
        ) : (
          <div className="heldout-evidence-grid">
            <div className="heldout-document-list" role="list">
              {reviewedCccdSessions.map((session, index) => (
                <button
                  className={
                    session.sessionId === activeCccdSession?.sessionId
                      ? "active"
                      : ""
                  }
                  key={session.sessionId}
                  onClick={() => setActiveCccdSessionId(session.sessionId)}
                  role="listitem"
                >
                  <span>CCCD-{String(index + 1).padStart(2, "0")}</span>
                  <strong>{session.originalFileName}</strong>
                  <small>
                    Ground Truth ✓ · Phase {session.phase11Version ?? "—"} ·{" "}
                    {session.recognizedTextLineCount} dòng ·{" "}
                    {pct(session.avgConfidence)}
                  </small>
                </button>
              ))}
            </div>
            <div className="heldout-preview">
              {activeCccdSession ? (
                <img
                  src={`${API_BASE}/user/source?id=${encodeURIComponent(
                    activeCccdSession.sessionId,
                  )}`}
                  alt={`CCCD thật đã review ${activeCccdSession.originalFileName}`}
                />
              ) : (
                <div className="native-heldout-file">
                  <strong>Chưa có session CCCD đã Ground Truth</strong>
                </div>
              )}
              {activeCccdSession && (
                <div className="heldout-preview-actions">
                  <div>
                    <strong>{activeCccdSession.originalFileName}</strong>
                    <span>
                      CCCD · Ground Truth ✓ · Phase{" "}
                      {activeCccdSession.phase11Version ?? "—"} · confidence{" "}
                      {pct(activeCccdSession.avgConfidence)}
                    </span>
                  </div>
                  <button
                    onClick={() =>
                      void openEvidenceSession(activeCccdSession.sessionId)
                    }
                  >
                    Mở OCR, field và JSON
                  </button>
                </div>
              )}
            </div>
            <EvidenceInspector
              detail={activeCccdEvidence}
              loading={cccdEvidenceLoading}
              error={cccdEvidenceError}
              view={evidenceInspectorView}
              onViewChange={setEvidenceInspectorView}
              downloads={
                activeCccdSession
                  ? [
                      {
                        label: "OCR JSON",
                        href: `${API_BASE}/user/download?id=${encodeURIComponent(
                          activeCccdSession.sessionId,
                        )}`,
                      },
                      ...(cccdEvidenceResult?.phase11_5
                        ? [
                            {
                              label: "Phase 11.5 Evidence",
                              href: `${API_BASE}/user/phase11-5-evidence?id=${encodeURIComponent(
                                activeCccdSession.sessionId,
                              )}`,
                            },
                          ]
                        : []),
                      {
                        label: "Business JSON",
                        href: cccdEvidenceResult?.phase11_5
                          ? `${API_BASE}/user/phase11-5-business?id=${encodeURIComponent(
                              activeCccdSession.sessionId,
                            )}`
                          : `${API_BASE}/user/phase15-business?id=${encodeURIComponent(
                              activeCccdSession.sessionId,
                            )}`,
                      },
                    ]
                  : []
              }
            />
          </div>
        )}
        {SHOW_HELDOUT ? (
          <div className="privacy-boundary">
            <strong>
              Phạm vi quyền hiện tại: local-only · publicReleaseAuthorized=
              {String(heldout?.publicReleaseAuthorized ?? false)}
            </strong>
            <p>
              Báo cáo Git chỉ công khai số liệu aggregate không chứa PII. Muốn
              đưa ảnh thô vào repository công khai phải bổ sung quyền phân phối
              công khai và sự đồng ý của chủ thể cho từng document ID.
            </p>
          </div>
        ) : null}
      </section>

      <section className="section next-section" id="next">
        <div className="section-heading">
          <div>
            <p className="eyebrow">RECOMMENDED NEXT</p>
            <h2>Giải quyết recognizer bằng bằng chứng thật</h2>
          </div>
          <p>
            Kết quả 18 tài liệu thật đã cho thấy lỗi không chỉ ở dấu tiếng Việt:
            classifier, reading order, field parser và table contract đều đang
            kéo metric xuống. Cần sửa theo tầng, không thể chỉ đổi một model.
          </p>
        </div>
        <div className="next-grid">
          {phase17Steps.map((step) => (
            <article key={step.order}>
              <span>0{step.order}</span>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </article>
          ))}
        </div>
        <div className="decision-banner">
          <div>
            <span>ĐIỂM QUYẾT ĐỊNH</span>
            <strong>Chỉ truyền dữ liệu sang workflow khi bằng chứng và accepted precision đạt gate.</strong>
          </div>
          <p>
            Business JSON hiện chỉ là đầu ra Camunda-ready local; chưa có API call
            hay process instance nào được tạo.
          </p>
        </div>
      </section>

      <footer>
        <span>HR OCR Baseline / local-only</span>
        <span>Python 3.10.11 / PaddleOCR 3.7.0 / PaddlePaddle 3.3.1</span>
      </footer>

      {selected && (
        <div className="drawer-backdrop" role="presentation" onClick={() => setSelected(null)}>
          <aside
            className="detail-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={`Chi tiết ${selected.sampleId}`}
            onClick={(event) => event.stopPropagation()}
          >
            <button className="drawer-close" onClick={() => setSelected(null)} aria-label="Đóng">
              ×
            </button>
            <p className="eyebrow">NATIVE OCR DETAIL</p>
            <h2>{selected.sampleId}</h2>
            <div className="profile-toggle" role="group" aria-label="Chọn phiên bản OCR">
              <button
                className={viewProfile === "phase7" ? "active" : ""}
                onClick={() => setViewProfile("phase7")}
              >
                Phase 7 improved
              </button>
              <button
                className={viewProfile === "baseline" ? "active" : ""}
                onClick={() => setViewProfile("baseline")}
              >
                Phase 5 baseline
              </button>
            </div>
            <div className="drawer-metrics">
              <div><span>Confidence</span><strong>{pct(viewProfile === "phase7" ? selected.avgConfidence : selected.baseline.avgConfidence)}</strong></div>
              <div><span>CER</span><strong>{decimal(viewProfile === "phase7" ? selected.cer : selected.baseline.cer)}</strong></div>
              <div><span>Exact</span><strong>{pct(viewProfile === "phase7" ? selected.exactMatchRate : selected.baseline.exactMatchRate)}</strong></div>
              <div><span>Duration</span><strong>{duration(Number(viewProfile === "phase7" ? selected.durationMs : selected.baseline.durationMs ?? 0))}</strong></div>
            </div>
            {detailError && <div className="api-warning">{detailError}</div>}
            {!detail && !detailError && <div className="loading-detail">Đang đọc private-data local…</div>}
            {detail && (
              <>
                <div className="source-line">
                  <span>Source</span>
                  <code>{detail.sourceRelativePath}</code>
                </div>
                {detail.hasVisualization && (
                  <div className="visualization">
                    {/* This URL is served only by the loopback API. */}
                    <img
                      src={`${API_BASE}/visualization?id=${encodeURIComponent(detail.sampleId)}&profile=${viewProfile}`}
                      alt={`Visualization bounding boxes của ${detail.sampleId}`}
                    />
                  </div>
                )}
                <div className="ocr-text">
                  <div>
                    <h3>Recognized text</h3>
                    <span>{detail.recognizedTexts.length} text lines</span>
                  </div>
                  {detail.recognizedTexts.length ? (
                    <ol>
                      {detail.recognizedTexts.map((text, index) => (
                        <li key={`${text}-${index}`}>
                          <span>{index + 1}</span>
                          <p>{text}</p>
                          <small>{pct(detail.recognitionScores[index] ?? null)}</small>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="empty-text">Không nhận ra text trong ảnh này.</p>
                  )}
                </div>
                {!!selected.mainErrors.length && (
                  <div className="error-fields">
                    <span>Main field errors</span>
                    <div>
                      {selected.mainErrors.map((error) => <code key={error}>{error}</code>)}
                    </div>
                  </div>
                )}
              </>
            )}
          </aside>
        </div>
      )}
    </main>
  );
}
