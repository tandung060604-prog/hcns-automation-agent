"use client";

import { useEffect, useMemo, useState } from "react";
import {
  pendingReviewCases,
  resumePendingReview,
} from "./review-queue.mjs";

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
  confidence: number | null;
  status: "accepted" | "needs_review" | "not_found";
  validation: {
    valid: boolean;
    rule: string;
    confidenceThreshold: number;
    labelMatchScore: number;
  };
  evidence: {
    engine: string;
    pageIndex: number;
    lineIndices: number[];
    bbox: number[][] | null;
    texts: string[];
  } | null;
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
  phase12?: {
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
      confidence: number;
      status: "accepted" | "needs_review";
      evidence: string[];
    };
    extraction: {
      fields: Record<string, IdentityField>;
      tables: Array<{
        name: string;
        columns: string[];
        rows: Array<{
          rowIndex: number;
          values: Record<string, IdentityField>;
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
  };
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
  reviewed?: boolean;
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
  CV: "CV",
  EMPLOYEE_INFORMATION_FORM: "Phiếu nhân viên",
  HR_DECISION: "Quyết định",
  TIMESHEET: "Bảng chấm công",
  LEAVE_REQUEST: "Đơn nghỉ phép",
  DEGREE: "Bằng cấp",
  DEGREE_CERTIFICATE: "Bằng cấp / chứng chỉ",
  GENERIC_PDF: "PDF tổng quát",
  GENERIC_DOCUMENT: "Tài liệu tổng quát",
  IDENTITY_DOCUMENT: "Giấy tờ định danh",
  PUBLIC_OCR: "Public OCR",
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

const phase13Steps = [
  {
    order: 1,
    title: "Chọn tài liệu thật có quyền xử lý",
    description:
      "Ưu tiên đơn nghỉ phép, hợp đồng và bảng chấm công; giữ toàn bộ file trong private-data.",
  },
  {
    order: 2,
    title: "Xác nhận ground truth",
    description:
      "Đối chiếu trực tiếp với tài liệu gốc và xác nhận từng field/table trước khi đo.",
  },
  {
    order: 3,
    title: "Đo lại theo từng loại",
    description:
      "So sánh Field Exact, Table Cell Accuracy, Completeness và accepted precision với tập tổng hợp.",
  },
  {
    order: 4,
    title: "Chốt quality gate Camunda",
    description:
      "Chỉ cho phép READY đi thẳng; mọi trường thiếu bằng chứng hoặc không chắc chắn phải vào human review.",
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

function phase11Label(result: UserResult) {
  return result.phase11_4 ? "11.4" : result.phase11_3 ? "11.3" : "11.2";
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
  const [viewProfile, setViewProfile] = useState<"phase7" | "baseline">("phase7");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [userResult, setUserResult] = useState<UserResult | null>(null);
  const [userSessions, setUserSessions] = useState<UserSessionSummary[]>([]);
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

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((response) => {
        if (!response.ok) throw new Error("offline");
        setApiOnline(true);
      })
      .catch(() => setApiOnline(false));
    refreshUserSessions();
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
    setIsUploading(true);
    setUploadError("");
    setUserResult(null);
    setDeleteArmed(false);
    const formData = new FormData();
    formData.append("file", uploadFile);
    try {
      const response = await fetch(`${API_BASE}/user/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "OCR local thất bại");
      setUserResult(payload as UserResult);
      setActiveUserPage(0);
      setTextView("corrected");
      loadPhase10Review((payload as UserResult).sessionId);
      refreshUserSessions();
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
      setUserResult(payload);
      setActiveUserPage(0);
      setTextView("corrected");
      loadPhase10Review(payload.sessionId);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Không tải được session");
    }
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
      setUserResult(payload as UserResult);
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
      setUserResult(null);
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
  const latestPrivateSession = userSessions[0] ?? null;

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Về đầu trang">
          <span className="brand-mark">HR</span>
          <span>OCR LAB</span>
        </a>
        <nav aria-label="Điều hướng chính">
          <a href="#phases">Phase 1-12</a>
          <a href="#metrics">Chất lượng</a>
          <a href="#upload">OCR tài liệu thật</a>
          <a href="#explorer">Khám phá mẫu</a>
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
        <figure className="hero-product">
          <div className="hero-product-frame">
            {latestPrivateSession ? (
              <img
                src={`${API_BASE}/user/visualization?id=${encodeURIComponent(
                  latestPrivateSession.sessionId,
                )}&page=0`}
                alt="Visualization OCR của tài liệu PII thật được xử lý trên máy local"
                onError={(event) => {
                  event.currentTarget.onerror = null;
                  event.currentTarget.src =
                    "/assets/hr-document-intelligence-context.webp";
                }}
              />
            ) : featuredSample ? (
              <img
                src={`${API_BASE}/visualization?id=${encodeURIComponent(
                  featuredSample.sampleId,
                )}&profile=phase7`}
                alt="Visualization OCR thật với bounding box trên tài liệu HCNS synthetic"
                onError={(event) => {
                  event.currentTarget.onerror = null;
                  event.currentTarget.src =
                    "/assets/hr-document-intelligence-context.webp";
                }}
              />
            ) : (
              <img
                src="/assets/hr-document-intelligence-context.webp"
                alt="Bối cảnh kiểm duyệt tài liệu HCNS trên máy local"
              />
            )}
          </div>
          <figcaption>
            {latestPrivateSession
              ? "Visualization từ tài liệu PII thật gần nhất. Chỉ hiển thị và xử lý trên máy local."
              : "Chưa có session PII thật. Đang hiển thị sample synthetic từ pipeline local."}
          </figcaption>
        </figure>
      </section>

      <section className="proof-strip" aria-label="Bằng chứng vận hành">
        <div>
          <span>Native JSON</span>
          <strong>{data.summary.nativeJsonCount}</strong>
        </div>
        <div>
          <span>OCR thành công</span>
          <strong>{pct(successRate)}</strong>
        </div>
        <div>
          <span>Ground Truth</span>
          <strong>{data.summary.matchedGroundTruthDocumentCount}/38</strong>
        </div>
        <div>
          <span>Runtime</span>
          <strong>
            {data.processing.ocrVersion} / {data.processing.device.toUpperCase()}
          </strong>
        </div>
      </section>

      <section className="section product-section" id="product">
        <figure className="product-context">
          <img
            src="/assets/hr-document-intelligence-context.webp"
            alt="Nhân sự kiểm tra tài liệu đã khử thông tin nhận diện trên giao diện OCR"
          />
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

        {phase14 && (
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
                  accept=".png,.jpg,.jpeg,.pdf,.docx,.xlsx"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                />
                <span className="upload-icon">＋</span>
                <strong>
                  {uploadFile ? uploadFile.name : "Kéo thả hoặc chọn tài liệu"}
                </strong>
                <p>
                  {uploadFile
                    ? `${(uploadFile.size / 1024 / 1024).toFixed(2)} MB`
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
              <button className="process-button" disabled={!uploadFile || isUploading}>
                {isUploading
                  ? "Đang OCR local… có thể mất vài phút"
                  : "Phân tích tài liệu"}
              </button>
              {uploadError && <div className="upload-error">{uploadError}</div>}
            </form>

            <div className="session-history">
              <div>
                <h3>Session đã lưu</h3>
                <span>{userSessions.length} session private</span>
              </div>
              {userSessions.length ? (
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
                          </small>
                        </span>
                        <b>{pct(session.avgConfidence)}</b>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>Chưa có tài liệu thật nào được lưu.</p>
              )}
            </div>
          </div>

          <div className="upload-result">
            {!userResult && !isUploading && (
              <div className="result-placeholder">
                <span>JSON</span>
                <h3>Kết quả sẽ xuất hiện tại đây</h3>
                <p>
                  Bao gồm raw OCR text, confidence, bounding boxes, field candidates,
                  visualization và processing metadata.
                </p>
              </div>
            )}
            {isUploading && (
              <div className="result-placeholder processing">
                <i />
                <h3>Đang nạp model và đọc tài liệu</h3>
                <p>Lần đầu có thể chậm hơn. Không đóng localhost trong khi xử lý.</p>
              </div>
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

                {userResult.phase12 && (
                  <div className="phase12-strip">
                    <div>
                      <span>PHASE 12 / INGESTION</span>
                      <strong>
                        {userResult.phase12.ingestion.sourceFormat} /{" "}
                        {userResult.phase12.ingestion.mode}
                      </strong>
                      <small>{userResult.phase12.ingestion.adapter}</small>
                    </div>
                    <div>
                      <span>HR DOCUMENT TYPE</span>
                      <strong>
                        {typeLabels[userResult.phase12.classification.documentType] ??
                          userResult.phase12.classification.documentType}
                      </strong>
                      <small>
                        {pct(userResult.phase12.classification.confidence)} confidence /{" "}
                        {userResult.phase12.classification.status}
                      </small>
                    </div>
                    <div>
                      <span>BUSINESS EXTRACTION</span>
                      <strong>{userResult.phase12.status}</strong>
                      <small>
                        {pct(
                          userResult.phase12.extraction.summary.documentCompleteness,
                        )}{" "}
                        completeness /{" "}
                        {userResult.phase12.extraction.summary.acceptedFieldCount}/
                        {userResult.phase12.extraction.summary.expectedFieldCount} accepted
                      </small>
                    </div>
                  </div>
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
                  {userResult.phase12 && (
                    <>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/phase12-canonical?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải Canonical JSON
                      </a>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/phase12-result?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải IDP JSON
                      </a>
                      <a
                        className="secondary-download"
                        href={`${API_BASE}/user/phase12-business?id=${encodeURIComponent(
                          userResult.sessionId,
                        )}`}
                        download
                      >
                        Tải Business JSON
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
            <p className="eyebrow">EXECUTION MAP</p>
            <h2>Phase 1 → Phase 12</h2>
          </div>
          <p>Mỗi phase có một đầu ra kiểm chứng được và dừng đúng điểm kiểm soát.</p>
        </div>
        <div className="phase-grid">
          {data.phases.map((phase) => (
            <article className="phase-card" key={phase.number}>
              <div className="phase-top">
                <span>{String(phase.number).padStart(2, "0")}</span>
                <b>{phase.status === "complete" ? "Complete" : "Needs review"}</b>
              </div>
              <h3>{phase.name}</h3>
              <p>{phase.summary}</p>
              <small>{phase.result}</small>
            </article>
          ))}
          <article className="phase-card">
            <div className="phase-top">
              <span>11</span>
              <b>Complete</b>
            </div>
            <h3>CCCD structured extraction</h3>
            <p>
              Chuẩn hóa hướng/phối cảnh, parser theo nhãn và tọa độ, crop riêng
              cho họ tên và địa chỉ, acceptance gate bảo thủ.
            </p>
            <small>
              Ground truth 001-029 đã được review; field không chắc chắn luôn
              chuyển sang needs_review.
            </small>
          </article>
          <article className="phase-card">
            <div className="phase-top">
              <span>12</span>
              <b>Complete</b>
            </div>
            <h3>Multi-format HR IDP</h3>
            <p>
              Ingest PDF native/scan/hybrid, DOCX, XLSX; phân loại tám nhóm HCNS
              và parser riêng cho biểu mẫu, văn bản và bảng.
            </p>
            <small>
              50/50 phân loại đúng; năm parser mục tiêu và 280/280 ô timesheet
              đạt exact trên tập tổng hợp.
            </small>
          </article>
        </div>
      </section>

      <section className="section metrics-section" id="metrics">
        <div className="section-heading">
          <div>
            <p className="eyebrow">MEASURED, NOT GUESSED</p>
            <h2>Chất lượng baseline</h2>
          </div>
          <p>Metric field-level trên 507 field instances; dấu tiếng Việt được giữ nguyên.</p>
        </div>
        <div className="metric-grid">
          <article className="metric-card accent">
            <span>CER ↓</span>
            <strong>{decimal(data.summary.cer)}</strong>
            <p>Character Error Rate</p>
            <small>Baseline {decimal(data.baselineSummary.cer)}</small>
          </article>
          <article className="metric-card">
            <span>WER ↓</span>
            <strong>{decimal(data.summary.wer)}</strong>
            <p>Word Error Rate</p>
            <small>Baseline {decimal(data.baselineSummary.wer)}</small>
          </article>
          <article className="metric-card">
            <span>EXACT MATCH ↑</span>
            <strong>{pct(data.summary.exactMatchRate)}</strong>
            <p>Field value xuất hiện nguyên vẹn</p>
            <small>Baseline {pct(data.baselineSummary.exactMatchRate)}</small>
          </article>
          <article className="metric-card">
            <span>FIELD PRESENCE ↑</span>
            <strong>{pct(data.summary.fieldPresenceRate)}</strong>
            <p>Exact hoặc CER ≤ 0.25</p>
            <small>Baseline {pct(data.baselineSummary.fieldPresenceRate)}</small>
          </article>
          <article className="metric-card dark">
            <span>MEAN DURATION</span>
            <strong>{duration(data.summary.durationMs.mean)}</strong>
            <p>P95 {duration(data.summary.durationMs.p95)} / CPU</p>
            <small>Baseline {duration(data.baselineSummary.durationMs.mean)}</small>
          </article>
        </div>
        <div className="performance-panel">
          <div className="panel-title">
            <div>
              <h3>CER theo loại tài liệu</h3>
              <p>Thấp hơn là tốt hơn</p>
            </div>
          <span>Phase 7 / 114 synthetic samples</span>
          </div>
          <div className="bars">
            {typePerformance.map((item) => (
              <div className="bar-row" key={item.name}>
                <span>{typeLabels[item.name] ?? item.name}</span>
                <div className="bar-track">
                  <i style={{ width: `${Math.min(item.cer / 0.25, 1) * 100}%` }} />
                </div>
                <b>{item.cer.toFixed(4)}</b>
              </div>
            ))}
          </div>
          <aside>
            <span>BEST</span>
            <strong>Employment Contract</strong>
            <b>CER 0.0713</b>
            <hr />
            <span>NEEDS WORK</span>
            <strong>Generic PDF</strong>
            <b>CER 0.2300</b>
          </aside>
        </div>
      </section>

      <section className="section explorer-section" id="explorer">
        <div className="section-heading">
          <div>
            <p className="eyebrow">RESULT EXPLORER</p>
            <h2>Khám phá từng mẫu</h2>
          </div>
          <p>Chọn một hàng để xem Native OCR text và visualization trực tiếp từ private-data.</p>
        </div>
        <div className="filters">
          <label className="search-box">
            <span>⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm document hoặc sample ID…"
            />
          </label>
          <label>
            <span>Loại tài liệu</span>
            <select value={type} onChange={(event) => setType(event.target.value)}>
              <option value="ALL">Tất cả</option>
              {types.map((name) => (
                <option key={name} value={name}>
                  {typeLabels[name] ?? name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Biến thể</span>
            <select value={variant} onChange={(event) => setVariant(event.target.value)}>
              <option value="ALL">Tất cả</option>
              {variants.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Trạng thái</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="ALL">Tất cả</option>
              <option value="SUCCESS">OCR success</option>
              <option value="FAILED">Không nhận ra text</option>
            </select>
          </label>
        </div>
        <div className="table-meta">
          <span>{filtered.length} / {data.samples.length} mẫu</span>
          <span>Click một hàng để xem chi tiết</span>
        </div>
        <div className="results-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sample</th>
                <th>Loại</th>
                <th>Biến thể</th>
                <th>Trạng thái</th>
                <th>Confidence</th>
                <th>CER</th>
                <th>Exact</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((sample) => (
                <tr key={sample.sampleId}>
                  <td>
                    <button onClick={() => setSelected(sample)}>{sample.sampleId}</button>
                  </td>
                  <td>{typeLabels[sample.documentType] ?? sample.documentType}</td>
                  <td><code>{sample.variant}</code></td>
                  <td>
                    <span className={`status-pill ${sample.ocrSuccess ? "success" : "failed"}`}>
                      {sample.ocrSuccess ? "Success" : "No text"}
                    </span>
                  </td>
                  <td>{pct(sample.avgConfidence)}</td>
                  <td>{decimal(sample.cer)}</td>
                  <td>{pct(sample.exactMatchRate)}</td>
                  <td>{duration(sample.durationMs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section next-section" id="next">
        <div className="section-heading">
          <div>
            <p className="eyebrow">RECOMMENDED NEXT</p>
            <h2>Phase 13: pilot trên tài liệu thật</h2>
          </div>
          <p>
            Phase 12 đã hoàn tất trên tập tổng hợp. Bước tiếp theo là đo lại cùng
            quality gate trên tài liệu thật do bạn có quyền xử lý.
          </p>
        </div>
        <div className="next-grid">
          {phase13Steps.map((step) => (
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
