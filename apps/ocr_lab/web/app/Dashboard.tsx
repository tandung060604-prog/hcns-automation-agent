"use client";
import { useEffect, useMemo, useState } from "react";
import {
  pendingReviewCases,
  resumePendingReview,
} from "./review-queue.mjs";
import ExternalDatasetReview from "./ExternalDatasetReview";
import ExternalDatasetPrediction from "./ExternalDatasetPrediction";
import LocalEvidenceOverview from "./LocalEvidenceOverview";
import OcrHoDiagnostic from "./OcrHoDiagnostic";

const SHOW_ADVANCED_DIAGNOSTICS =
  import.meta.env.VITE_ADVANCED_DIAGNOSTICS === "true";
const SHOW_GROUND_TRUTH_REVIEW = SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_GROUND_TRUTH_REVIEW === "true";
const SHOW_EXTERNAL_DATASET_REVIEW =
  SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_EXTERNAL_DATASET_REVIEW === "true";
const SHOW_DATA31_COVERAGE_REVIEW =
  SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_DATA31_COVERAGE_REVIEW === "true";
const SHOW_LEGACY_EXPLORER_TABS =
  SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_LEGACY_EXPLORER_TABS === "true";
const SHOW_OCR_HO_SHADOW_UAT =
  SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_OCR_HO_SHADOW_UAT === "true";
const SHOW_OCR_HO_DIAGNOSTIC_GT =
  SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_OCR_HO_DIAGNOSTIC_GT === "true";
const SHOW_LEGACY_UPLOAD =
  SHOW_ADVANCED_DIAGNOSTICS &&
  import.meta.env.VITE_SHOW_LEGACY_UPLOAD === "true";

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
  processing?: {
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

type CccdGroundTruthField = {
  value: string;
  notPresent: boolean;
};

type CccdGroundTruthReviewSummary = {
  schemaVersion: string;
  datasetId: string;
  datasetDigest: string;
  documentCount: number;
  sourceDocumentCount: number;
  excludedDocumentCount: number;
  fieldCount: number;
  fields: string[];
  groundTruthStatus: string;
  evaluationStatus: string;
  evaluation?: {
    evaluationKind?: string;
    evaluatedAt?: string;
    metrics: Record<string, Record<string, number>>;
    promotionGateStatus?: string | null;
  } | null;
  predictionsHiddenDuringReview: true;
  localOnly: true;
  documentIds: string[];
  documents: Array<{
    documentId: string;
    documentIndex: number;
    sourceFormat: string;
    sourceFile: string;
    previewAvailable: boolean;
    reviewStatus: string;
    disposition: "IN_SCOPE_FRONT" | "OUT_OF_SCOPE_BACK";
    exclusionReason?: string;
    reviewedFieldCount: number;
    fieldCount: number;
  }>;
  canLock: boolean;
  canEvaluate: boolean;
};

type CccdGroundTruthReviewDocument = {
  schemaVersion: string;
  documentId: string;
  documentIndex: number;
  sourceFormat: string;
  sourceFile: string;
  previewAvailable: boolean;
  reviewStatus: string;
  disposition: "IN_SCOPE_FRONT" | "OUT_OF_SCOPE_BACK";
  exclusionReason?: string;
  fields: Record<string, CccdGroundTruthField>;
  verificationAssertions: {
    comparedWithImage: boolean;
    allTextChecked: boolean;
  };
  predictionsHidden: true;
};

type CccdGroundTruthEvaluation = {
  status: string;
  evaluationKind: string;
  documentCount: number;
  metrics: Record<string, Record<string, number>>;
  promotionGate: {
    status: string;
    checks: Record<string, boolean>;
    exactImprovementCount?: number;
    exactRegressionCount?: number;
  };
};

type CccdEvaluationPredictionField = {
  value: string | null;
  asciiValue: string | null;
  status: string | null;
  confidence: number | null;
  errorSignals: string[];
  selectionMode: string | null;
  evidence: {
    pageIndex?: number | null;
    bbox?: number[] | null;
    candidateCount?: number;
  };
};

type CccdEvaluationComparison = {
  status: "EXACT" | "MISMATCH" | "NOT_IN_SOURCE";
  strictExact: boolean | null;
  asciiExact: boolean | null;
  errorClass: string | null;
};

type CccdGroundTruthEvaluationDetail = {
  schemaVersion: string;
  evaluationKind: string;
  evaluatedAt: string;
  documentId: string;
  documentIndex: number;
  sourceFile: string;
  documentCount: number;
  localOnly: true;
  predictionsHiddenDuringReview: true;
  fields: Record<
    string,
    {
      groundTruth: { value: string | null; notPresent: boolean };
      phase11_5: CccdEvaluationPredictionField;
      phase11_6: CccdEvaluationPredictionField;
      comparison: {
        phase11_5: CccdEvaluationComparison;
        phase11_6: CccdEvaluationComparison;
      };
    }
  >;
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
  predictionLabel?: string;
  predictionNotice?: string;
};

type OcrHoShadowSummary = {
  schemaVersion: string;
  localOnly: true;
  containsRealPII: true;
  groundTruthLoaded: false;
  predictionMode: "SHADOW_REVIEW_ONLY";
  candidateVersion: string;
  policyId: string | null;
  datasetRole: string | null;
  targetFields: string[];
  protectedFields: string[];
  documentCount: number;
  metrics: Record<string, Record<string, number>>;
  promotionGate: {
    status?: string;
    productionPromotionAllowed?: boolean;
    exactImprovementCount?: number;
    exactRegressionCount?: number;
    schemaErrorCount?: number;
    manualReviewFieldCount?: number;
  };
  reviewCounts: Record<string, number>;
  documents: Array<{
    documentId: string;
    documentIndex: number;
    sourceFile: string;
    sourceFormat: string;
    pageCount: number;
    previewAvailable: boolean;
    reviewDecision: string;
    reviewedAt: string | null;
  }>;
};

type OcrHoShadowField = {
  value: string | null;
  asciiValue: string | null;
  status: string | null;
  asciiStatus: string | null;
  confidence: number | null;
  errorSignals: string[];
  selectionMode: string | null;
  evidence: {
    pageIndex: number | null;
    bbox: number[];
    candidateCount: number;
    recognizerProfiles: string[];
  };
};

type OcrHoShadowDetail = {
  schemaVersion: string;
  localOnly: true;
  containsRealPII: true;
  groundTruthLoaded: false;
  predictionMode: "SHADOW_REVIEW_ONLY";
  candidateVersion: string | null;
  policyId: string | null;
  documentId: string;
  documentIndex: number;
  sourceFile: string;
  sourceFormat: string;
  pageCount: number;
  previewAvailable: boolean;
  sourceReference: string;
  baselineReference: string;
  candidateReference: string;
  candidatePolicyLock: Record<string, unknown>;
  fields: Record<
    string,
    {
      targetField: boolean;
      changed: boolean;
      baseline: OcrHoShadowField;
      candidate: OcrHoShadowField;
    }
  >;
  review: {
    decision: string;
    reviewedAt: string;
    reviewer: string;
    assertions: Record<string, boolean>;
    note: string;
  } | null;
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
    recognizerVersion?: string;
    orientationPolicy?: string;
    evaluationScope?: string;
    status: "PASS" | "NEEDS_REVIEW" | "NOT_APPLICABLE";
    orientation: {
      strategy: string;
      supportedOrientations?: number[];
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
        manualReviewRequired?: boolean;
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
  parserId: string;
  parserVersion: string;
  lifecycle: string;
  supportedFileTypes: string[];
  requiredFields: string[];
  optionalFields: string[];
};

type RuntimePipeline = {
  documentType: string;
  templateId: string;
  templateVersion: string;
  parserId: string;
  parserVersion: string;
  supportedFileTypes: string[];
  lifecycle: string;
};

type RuntimeHealth = {
  runtimeProfile: string;
  templateOcrBackend: string;
  templateOcrProfile: string;
  backendAvailable: boolean;
  templateOcrModelLoaded: boolean;
  pipelines: RuntimePipeline[];
};

type TemplateProcessingResult = {
  status: "SUCCESS";
  documentType: string;
  templateId: string;
  templateVersion: string;
  templateParserId: string;
  templateParserVersion: string;
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
  processing: {
    sourceFormat: string;
    parserName: string;
    parserVersion: string;
    usesOcr: boolean;
    ocrEngine: string | null;
    ocrVersion?: string | null;
    ocrModels?: string[];
    ocrDevice?: string | null;
    ocrProfile?: string;
    ocrConfidence: number | null;
    processedAt?: string;
    originalFileName?: string;
    ocrFieldEvidence?: Array<{
      field?: string;
      confidence?: number;
      box?: unknown;
      recognizer?: string;
      reason?: string;
    }>;
  };
  camundaVariables: Record<string, unknown>;
};

type TemplateComparisonStatus =
  | "EXACT"
  | "ACCEPTED"
  | "MISMATCH"
  | "MISSING"
  | "NEEDS_REVIEW";

type TemplateComparison = {
  schemaVersion: string;
  scope: "CURRENT_FILE";
  documentId: string;
  matchingPolicyVersion: string;
  comparedAt: string;
  groundTruth: Record<string, unknown>;
  fields: Array<{
    name: string;
    prediction: unknown;
    groundTruth: unknown;
    status: TemplateComparisonStatus;
    confidence: number | null;
    evidence: Record<string, unknown>;
    matchType: string | null;
    coverage: number | null;
    diagnosis: string | null;
  }>;
  summary: {
    totalFields: number;
    comparedFields: number;
    exactFields: number;
    acceptedFields: number;
    wrongFields: number;
    mismatchFields: number;
    missingFields: number;
    needsReviewFields: number;
    decision: "HOLD" | "PASS";
  };
  workflow: {
    recommendedAction: string;
    promotionAllowed: false;
    note: string;
  };
};

type CamundaReviewTask = {
  taskId: string;
  role: "employee" | "hr";
  taskName: string;
  documentId: string;
  documentType: string;
  created: string;
  inspectable: boolean;
};

type CamundaCaseStatus = {
  processInstanceId: string;
  applicationId: string | null;
  documentType: string;
  state:
    | "PROCESSING"
    | "AWAITING_USER_REVIEW"
    | "AWAITING_HR_REVIEW"
    | "REUPLOAD_REQUIRED"
    | "COMPLETED"
    | "REJECTED"
    | "INCIDENT";
  taskId: string | null;
  taskName: string | null;
  incidentCount: number;
  tasklistUrl: string;
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
  "schemaVersion",
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
  CERTIFICATE: "IELTS / chứng chỉ",
  EMPLOYEE_INFORMATION_FORM: "Phiếu nhân viên",
  EMPLOYEE_INFO_UPDATE: "Phiếu cập nhật nhân sự",
  EMPLOYEE_MASTER_LIST: "Danh sách nhân sự",
  ONBOARDING_CHECKLIST: "Checklist tiếp nhận",
  TRAINING_ATTENDANCE: "Danh sách đào tạo",
  HR_DECISION: "Quyết định",
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
  full_name: "Họ và tên (v2)",
  phone_number: "Số điện thoại (v2)",
  desired_role: "Vị trí mong muốn",
  years_experience: "Số năm kinh nghiệm",
  contract_number: "Số hợp đồng",
  contract_sign_date: "Ngày ký hợp đồng",
  effective_date: "Ngày hiệu lực",
  probation_end_date: "Ngày kết thúc thử việc",
  employer_name: "Tên người sử dụng lao động",
  employer_representative: "Đại diện người sử dụng lao động",
  employee_name: "Tên người lao động",
  employee_id_number: "Mã định danh người lao động",
  job_title: "Chức danh công việc",
  workplace: "Nơi làm việc",
  weekly_hours: "Giờ làm việc mỗi tuần",
  probation_salary_monthly: "Lương thử việc hàng tháng",
  allowances_summary: "Tóm tắt phụ cấp",
  salary_payment_schedule: "Kỳ trả lương",
  recipient_name: "Tên người nhận chứng chỉ",
  credential_id: "Mã chứng chỉ",
  credential_type: "Loại chứng chỉ",
  overall_score: "Điểm tổng IELTS",
  issue_date: "Ngày cấp / ngày thi",
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

function CccdEvaluationInspector({
  detail,
  loading,
  error,
}: {
  detail: CccdGroundTruthEvaluationDetail | null;
  loading: boolean;
  error: string;
}) {
  if (loading) {
    return (
      <div className="ground-truth-evaluation-inspector" data-testid="ground-truth-evaluation-inspector">
        <strong>Đang đọc output sau evaluate-once…</strong>
      </div>
    );
  }
  if (error) {
    return (
      <div className="ground-truth-evaluation-inspector error" data-testid="ground-truth-evaluation-inspector">
        <strong>Không đọc được output</strong>
        <span>{error}</span>
      </div>
    );
  }
  if (!detail) return null;
  return (
    <div className="ground-truth-evaluation-inspector" data-testid="ground-truth-evaluation-inspector">
      <div className="ground-truth-evaluation-inspector-heading">
        <div>
          <strong>OUTPUT THẬT SAU EVALUATE-ONCE</strong>
          <span>{detail.sourceFile} · {detail.documentCount} ảnh trong metric</span>
        </div>
        <small>Chỉ hiển thị local sau khi Ground Truth đã khóa.</small>
      </div>
      <div className="ground-truth-evaluation-table" role="table">
        <div className="ground-truth-evaluation-row heading" role="row">
          <span>FIELD</span>
          <span>GROUND TRUTH</span>
          <span>PHASE 11.5</span>
          <span>PHASE 11.6</span>
          <span>CHẨN ĐOÁN</span>
        </div>
        {Object.entries(detail.fields).map(([fieldName, field]) => {
          const phase11_6 = field.phase11_6;
          const comparison = field.comparison.phase11_6;
          const rowClass = comparison.status.toLowerCase();
          const bbox = phase11_6.evidence.bbox?.join(", ") ?? "—";
          return (
            <div className={`ground-truth-evaluation-row ${rowClass}`} key={fieldName} role="row">
              <strong>{identityFieldLabels[fieldName] ?? fieldName}</strong>
              <span>{evidenceValue(field.groundTruth.value)}</span>
              <span>{evidenceValue(field.phase11_5.value)}</span>
              <span>{evidenceValue(phase11_6.value)}</span>
              <span>
                <b>{comparison.errorClass ?? comparison.status}</b>
                <small>
                  {phase11_6.status ?? "—"} · {phase11_6.confidence == null ? "—" : `${(phase11_6.confidence * 100).toFixed(1)}%`} · ROI [{bbox}]
                </small>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function OcrHoShadowInspector({
  detail,
  loading,
  error,
  onReviewed,
}: {
  detail: OcrHoShadowDetail | null;
  loading: boolean;
  error: string;
  onReviewed: () => void;
}) {
  const [decision, setDecision] = useState("NEEDS_FOLLOWUP");
  const [note, setNote] = useState("");
  const [assertions, setAssertions] = useState({
    comparedWithSource: false,
    checkedChangedFields: false,
    confirmedManualReview: false,
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset local UAT form for the selected evidence document.
    setDecision(detail?.review?.decision ?? "NEEDS_FOLLOWUP");
    setNote(detail?.review?.note ?? "");
    setAssertions({
      comparedWithSource: detail?.review?.assertions?.comparedWithSource ?? false,
      checkedChangedFields: detail?.review?.assertions?.checkedChangedFields ?? false,
      confirmedManualReview: detail?.review?.assertions?.confirmedManualReview ?? false,
    });
    setSaveError("");
  }, [detail?.documentId, detail?.review?.reviewedAt]);

  if (loading) {
    return (
      <aside className="evidence-inspector shadow-uat-inspector" data-testid="ocr-ho-shadow-inspector">
        <div className="evidence-inspector-state">Đang tải shadow evidence…</div>
      </aside>
    );
  }
  if (error) {
    return (
      <aside className="evidence-inspector shadow-uat-inspector error" data-testid="ocr-ho-shadow-inspector">
        <div className="evidence-inspector-state error">{error}</div>
      </aside>
    );
  }
  if (!detail) return null;

  const changedFields = Object.entries(detail.fields).filter(([, field]) => field.changed);
  const value = (field: OcrHoShadowField) => field.value ?? "—";
  const saveReview = async () => {
    if (
      saving ||
      !assertions.comparedWithSource ||
      !assertions.checkedChangedFields ||
      !assertions.confirmedManualReview
    ) {
      return;
    }
    setSaving(true);
    setSaveError("");
    try {
      const response = await fetch(
        `${API_BASE}/ocr-ho-v2/shadow/review?id=${encodeURIComponent(detail.documentId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, note, assertions }),
        },
      );
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không lưu được shadow UAT");
      onReviewed();
    } catch (reviewError) {
      setSaveError(
        reviewError instanceof Error
          ? reviewError.message
          : "Không lưu được shadow UAT local.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <aside className="evidence-inspector shadow-uat-inspector" aria-live="polite" data-testid="ocr-ho-shadow-inspector">
      <header>
        <div>
          <span>SHADOW UAT · LOCAL-ONLY</span>
          <strong>OCR-HO-V2 v{detail.candidateVersion ?? "11.10.0"}</strong>
        </div>
        <small>{detail.predictionMode} · không nạp Ground Truth</small>
      </header>
      <div className="shadow-uat-banner">
        <strong>Ảnh nguồn → baseline → candidate</strong>
        <span>
          Policy: {detail.policyId ?? "phase11.8-v2-address-token-consensus"} · Candidate chỉ để review,
          không thay đổi output chính và luôn MANUAL_REVIEW.
        </span>
      </div>
      <div className="shadow-uat-table" role="table">
        <div className="shadow-uat-row heading" role="row">
          <span>FIELD</span>
          <span>BASELINE 11.5</span>
          <span>CANDIDATE {detail.candidateVersion ?? "11.10.0"}</span>
          <span>PROVENANCE</span>
        </div>
        {Object.entries(detail.fields).map(([fieldName, field]) => (
          <div
            className={`shadow-uat-row ${field.changed ? "changed" : ""}`}
            key={fieldName}
            role="row"
          >
            <strong>
              {fieldName}
              <small>{field.targetField ? "TARGET" : "PROTECTED"}</small>
            </strong>
            <span>{value(field.baseline)}</span>
            <span>
              {value(field.candidate)}
              <small data-status={field.candidate.status ?? undefined}>
                {field.candidate.status ?? "—"}
              </small>
            </span>
            <span>
              {field.changed ? "changed" : "unchanged"} · ROI [{field.candidate.evidence.bbox.join(", ") || "—"}]
              <small>
                {field.candidate.confidence == null
                  ? "confidence —"
                  : `confidence ${(field.candidate.confidence * 100).toFixed(1)}%`}
                {field.candidate.evidence.recognizerProfiles.length
                  ? ` · ${field.candidate.evidence.recognizerProfiles.join(", ")}`
                  : ""}
              </small>
            </span>
          </div>
        ))}
      </div>
      <div className="shadow-uat-review-form">
        <div>
          <strong>Review thay đổi ({changedFields.length} field)</strong>
          <span>Đối chiếu trực tiếp với ảnh bên trái; không dùng Ground Truth để quyết định.</span>
        </div>
        <div className="shadow-uat-decision-row">
          {[
            ["APPROVE_SHADOW", "Chấp nhận shadow"],
            ["REJECT_SHADOW", "Từ chối candidate"],
            ["NEEDS_FOLLOWUP", "Cần xử lý tiếp"],
          ].map(([option, label]) => (
            <label key={option}>
              <input
                type="radio"
                name={`shadow-decision-${detail.documentId}`}
                value={option}
                checked={decision === option}
                onChange={() => setDecision(option)}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="shadow-uat-assertions">
          {([
            ["comparedWithSource", "Đã đối chiếu ảnh nguồn"],
            ["checkedChangedFields", "Đã kiểm tra các field changed"],
            ["confirmedManualReview", "Xác nhận vẫn MANUAL_REVIEW"],
          ] as const).map(([name, label]) => (
            <label key={name}>
              <input
                type="checkbox"
                checked={assertions[name]}
                onChange={(event) =>
                  setAssertions((current) => ({ ...current, [name]: event.target.checked }))
                }
              />
              {label}
            </label>
          ))}
        </div>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={1000}
          placeholder="Ghi chú review local (tuỳ chọn)"
          aria-label="Ghi chú shadow UAT"
        />
        {saveError ? <small className="shadow-uat-error">{saveError}</small> : null}
        <button
          className="save-review"
          type="button"
          onClick={() => void saveReview()}
          disabled={
            saving ||
            !assertions.comparedWithSource ||
            !assertions.checkedChangedFields ||
            !assertions.confirmedManualReview
          }
        >
          {saving ? "Đang lưu…" : detail.review ? "Cập nhật shadow review" : "Lưu shadow review"}
        </button>
      </div>
    </aside>
  );
}

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
      "Huấn luyện/fine-tune recognizer hoặc crop policy trên dữ liệu development riêng; tuyệt đối không chỉnh theo benchmark held-out đã tiêu thụ.",
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
  const selectedPrediction = detail?.prediction;
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
      {detail?.predictionLabel ? (
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
              groundTruth: detail.groundTruth,
              prediction: selectedPrediction,
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

function phase11Label(result: UserResult) {
  if (result.phase11?.version === "1.1.0") {
    return "1.1";
  }
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

function TemplateDocumentPreview({
  filename,
  previewUrl,
  result,
}: {
  filename: string;
  previewUrl: string;
  result: TemplateProcessingResult | null;
}) {
  const extension = filename.split(".").pop()?.toLocaleLowerCase() ?? "";
  const sourceFormat = result?.processing.sourceFormat;
  const isImage =
    ["png", "jpg", "jpeg"].includes(extension) || sourceFormat === "IMAGE";
  const isPdf =
    extension === "pdf" ||
    sourceFormat === "PDF_TEXT" ||
    sourceFormat === "PDF_SCAN";

  return (
    <section
      className="template-document-preview"
      aria-label="Bản xem trước tài liệu"
      data-testid="template-document-preview"
    >
      <header>
        <div>
          <span>TÀI LIỆU ĐẦU VÀO</span>
          <strong>{filename || "Chưa chọn tài liệu"}</strong>
        </div>
        {filename ? <small>{extension.toUpperCase() || sourceFormat}</small> : null}
      </header>
      <div className="template-document-canvas">
        {!previewUrl ? (
          <div className="template-preview-empty">
            <span>01</span>
            <strong>Chọn tài liệu để xem trước</strong>
            <p>Ảnh và PDF sẽ hiển thị tại đây trước khi trích xuất.</p>
          </div>
        ) : isImage ? (
          <img src={previewUrl} alt={`Bản xem trước ${filename}`} />
        ) : isPdf ? (
          <iframe src={previewUrl} title={`Bản xem trước ${filename}`} />
        ) : (
          <div className="template-preview-file">
            <span>DOCX</span>
            <strong>{filename}</strong>
            <p>
              DOCX sẽ được đọc trực tiếp bằng native parser. Nội dung trích xuất
              xuất hiện ở khung kết quả bên cạnh.
            </p>
          </div>
        )}
      </div>
      {result ? (
        <footer>
          <span>{result.processing.parserName}</span>
          <strong>{result.quality.recommendedAction}</strong>
        </footer>
      ) : null}
    </section>
  );
}

function TemplateComparisonPanel({ result }: { result: TemplateProcessingResult }) {
  const fields = Object.entries(result.data).filter(
    ([name]) => !TEMPLATE_RESULT_META_FIELDS.has(name),
  );
  const documentId = result.data.documentId;
  const [groundTruthDraft, setGroundTruthDraft] = useState<Record<string, string>>({});
  const [comparison, setComparison] = useState<TemplateComparison | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [comparisonError, setComparisonError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/documents/comparison?id=${encodeURIComponent(documentId)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: TemplateComparison | null) => {
        if (cancelled || !payload) return;
        setComparison(payload);
        setGroundTruthDraft(
          Object.fromEntries(
            Object.entries(payload.groundTruth).map(([name, value]) => [
              name,
              value === null || value === undefined ? "" : String(value),
            ]),
          ),
        );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const compare = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsComparing(true);
    setComparisonError("");
    try {
      const groundTruth = Object.fromEntries(
        fields.map(([name]) => [name, groundTruthDraft[name]?.trim() || null]),
      );
      const response = await fetch(`${API_BASE}/api/documents/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ documentId, groundTruth }),
      });
      const payload = (await response.json()) as TemplateComparison & { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không đối chiếu được file hiện tại");
      setComparison(payload);
    } catch (error) {
      setComparisonError(
        error instanceof Error ? error.message : "Không đối chiếu được file hiện tại.",
      );
    } finally {
      setIsComparing(false);
    }
  };

  const comparisonByField = new Map(
    comparison?.fields.map((field) => [field.name, field]) ?? [],
  );
  const processedAt = result.processing.processedAt
    ? new Date(result.processing.processedAt).toLocaleString("vi-VN")
    : "Phiên hiện tại";

  return (
    <section className="template-comparison" aria-label="Đối chiếu kết quả file hiện tại">
      <header className="template-comparison-head">
        <div>
          <span>ĐỐI CHIẾU KẾT QUẢ · CURRENT FILE</span>
          <h4>Prediction và Ground Truth theo từng field</h4>
          <small>Ground Truth do người review nhập, chỉ lưu trong session localhost.</small>
        </div>
        <strong className={`comparison-decision ${comparison?.summary.decision === "PASS" ? "pass" : "hold"}`}>
          {comparison?.summary.decision ?? "HOLD"}
        </strong>
      </header>

      <div className="comparison-scope-strip single">
        <div>
          <span>FILE HIỆN TẠI</span>
          <strong>
            {comparison
              ? `${comparison.summary.exactFields} exact · ${comparison.summary.wrongFields} sai`
              : "Chưa nhập Ground Truth"}
          </strong>
          <small>{processedAt} · ID {documentId.slice(0, 8)}</small>
        </div>
      </div>

      <div className="algorithm-metadata" data-testid="template-algorithm-metadata">
        <span>Template {result.templateVersion}</span>
        <span>Parser {result.templateParserId} · {result.templateParserVersion}</span>
        <span>Intake {result.processing.parserName} {result.processing.parserVersion}</span>
        <span>
          {result.processing.usesOcr
            ? `${result.processing.ocrEngine ?? "OCR local"} ${result.processing.ocrVersion ?? ""}`
            : "Native parser · không OCR"}
        </span>
        {result.processing.usesOcr && result.processing.ocrModels?.length ? (
          <span>Models {result.processing.ocrModels.join(" + ")}</span>
        ) : null}
        {result.processing.usesOcr && result.processing.ocrDevice ? (
          <span>Device {result.processing.ocrDevice}</span>
        ) : null}
        <span>Profile {result.processing.ocrProfile ?? "native-text"}</span>
        <span>Matching {comparison?.matchingPolicyVersion ?? "2.1.0"}</span>
      </div>

      <form onSubmit={compare}>
        <div className="comparison-field-list">
          <div className="comparison-field-heading">
            <span>Field</span>
            <span>Prediction</span>
            <span>Ground Truth</span>
            <span>Confidence / Evidence</span>
            <span>Kết quả</span>
          </div>
          {fields.map(([name, prediction]) => {
            const fieldComparison = comparisonByField.get(name);
            const evidence = fieldComparison?.evidence ?? {};
            return (
              <div className="comparison-field-row" key={name}>
                <div>
                  <strong>{businessFieldLabels[name] ?? name}</strong>
                  <small>{name}</small>
                </div>
                <span>{formatTemplateValue(prediction)}</span>
                <textarea
                  aria-label={`Ground Truth ${name}`}
                  value={groundTruthDraft[name] ?? ""}
                  onChange={(event) =>
                    setGroundTruthDraft((current) => ({
                      ...current,
                      [name]: event.target.value,
                    }))
                  }
                  placeholder="Để trống nếu không có trong nguồn"
                  rows={2}
                />
                <div className="comparison-evidence">
                  <strong>{pct(fieldComparison?.confidence ?? result.quality.confidence)}</strong>
                  <small>
                    {typeof evidence.recognizer === "string"
                      ? evidence.recognizer
                      : result.processing.usesOcr
                        ? "OCR cấp tài liệu · chưa có bbox field"
                        : "Native parser · không có bbox field"}
                  </small>
                  {fieldComparison?.matchType ? <small>{fieldComparison.matchType}</small> : null}
                </div>
                <span
                  className={`comparison-status ${(fieldComparison?.status ?? "NEEDS_REVIEW").toLocaleLowerCase()}`}
                >
                  {fieldComparison?.status ?? "NEEDS_REVIEW"}
                </span>
              </div>
            );
          })}
        </div>
        <div className="comparison-actions">
          <div>
            {comparison ? (
              <span>
                Đã chấm {comparison.summary.comparedFields}/{comparison.summary.totalFields} field · Exact {comparison.summary.exactFields} · Accepted {comparison.summary.acceptedFields} · Sai {comparison.summary.wrongFields}
              </span>
            ) : (
              <span>Nhập Ground Truth từ tài liệu nguồn rồi chạy đối chiếu.</span>
            )}
            <small>PASS không đồng nghĩa tự duyệt nghiệp vụ; promotion luôn bị khóa.</small>
          </div>
          <button type="submit" disabled={isComparing} data-testid="compare-current-file-button">
            {isComparing ? "Đang đối chiếu…" : comparison ? "Đối chiếu lại" : "Đối chiếu kết quả"}
          </button>
        </div>
        {comparisonError ? <p className="comparison-error">{comparisonError}</p> : null}
      </form>
    </section>
  );
}

function TemplateResultPanel({
  result,
  filename,
  deleteArmed,
  onDelete,
  onStartCamunda,
  camundaStatus,
  camundaCase,
  onRefreshCamunda,
}: {
  result: TemplateProcessingResult;
  filename: string;
  deleteArmed: boolean;
  onDelete: () => void;
  onStartCamunda: () => void;
  camundaStatus: string;
  camundaCase: CamundaCaseStatus | null;
  onRefreshCamunda: () => void;
}) {
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

      <TemplateComparisonPanel key={result.data.documentId} result={result} />

      <details className="template-json">
        <summary>Xem JSON đầy đủ</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>

      <div className="result-actions template-result-actions">
        {["LEAVE_REQUEST", "OVERTIME_REQUEST", "CV", "CERTIFICATE", "EMPLOYMENT_CONTRACT"].includes(result.documentType) ? (
          <button type="button" onClick={onStartCamunda}>
            Đưa vào Camunda
          </button>
        ) : null}
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
      {camundaStatus ? <p className="review-help">{camundaStatus}</p> : null}
      {camundaCase ? (
        <div className="camunda-case-status" data-state={camundaCase.state}>
          <div>
            <span>CAMUNDA LOCAL SHADOW</span>
            <strong>{camundaCase.state.replaceAll("_", " ")}</strong>
            <small>
              {camundaCase.documentType} · process {camundaCase.processInstanceId.slice(0, 12)}…
              {camundaCase.taskName ? ` · ${camundaCase.taskName}` : ""}
            </small>
          </div>
          <div>
            <small>Incident: {camundaCase.incidentCount}</small>
            <button type="button" onClick={onRefreshCamunda}>Cập nhật trạng thái</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function RoleReviewQueue({
  tasks,
  onInspect,
  onReview,
}: {
  tasks: CamundaReviewTask[];
  onInspect: (documentId: string) => void;
  onReview: (task: CamundaReviewTask, decision: string) => void;
}) {
  const groups = [
    {
      role: "employee" as const,
      title: "Người nộp hồ sơ",
      description: "Xem lại thông tin đã trích xuất trước khi xác nhận hoặc chuyển cho HCNS.",
      actions: [["CONFIRMED", "Xác nhận chính xác"], ["UNRESOLVED", "Chuyển HCNS"]],
    },
    {
      role: "hr" as const,
      title: "HCNS",
      description: "Đối chiếu hồ sơ gốc và kết quả trích xuất, sau đó đưa ra quyết định xử lý.",
      actions: [["CONFIRMED", "Chấp nhận"], ["REQUEST_REUPLOAD", "Yêu cầu tải lại"], ["REJECTED", "Từ chối"]],
    },
  ];
  return (
    <section className="section role-review-section" id="roles">
      <div className="section-heading">
        <div>
          <p className="eyebrow">HÀNG ĐỢI KIỂM TRA</p>
          <h2>Phân công rõ người, rõ việc</h2>
        </div>
        <p>Chi tiết hồ sơ được kiểm tra trên máy nội bộ. Quyết định được gửi sang Camunda để lưu vết và điều phối bước tiếp theo.</p>
      </div>
      <div className="role-review-grid">
        {groups.map((group) => {
          const roleTasks = tasks.filter((task) => task.role === group.role);
          return <article className="role-review-card" key={group.role}>
            <header><span>{group.role === "employee" ? "01" : "02"}</span><div><h3>{group.title}</h3><p>{group.description}</p></div></header>
            <strong className="role-count">{roleTasks.length} việc cần xử lý</strong>
            {roleTasks.length ? <ul>{roleTasks.map((task) => <li key={task.taskId}>
              <div><small>{task.documentType}</small><b>{task.taskName}</b><code>{task.documentId.slice(0, 8)}…</code></div>
              <div className="role-actions"><button type="button" disabled={!task.inspectable} title={task.inspectable ? undefined : "Case này không có session local để xem chi tiết"} onClick={() => onInspect(task.documentId)}>{task.inspectable ? "Kiểm tra local" : "Không có session local"}</button>{group.actions.map(([decision, label]) => <button type="button" key={decision} onClick={() => onReview(task, decision)}>{label}</button>)}</div>
            </li>)}</ul> : <p className="role-empty">Chưa có task ở bước này.</p>}
          </article>;
        })}
      </div>
    </section>
  );
}

export default function Dashboard({ data }: { data: DashboardData }) {
  const showLegacyUpload = SHOW_LEGACY_UPLOAD;
  const [query, setQuery] = useState("");
  const [type, setType] = useState("ALL");
  const [variant, setVariant] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [selected, setSelected] = useState<Sample | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [apiOnline, setApiOnline] = useState(false);
  const [ocrHoShadow, setOcrHoShadow] = useState<OcrHoShadowSummary | null>(null);
  const [ocrHoShadowError, setOcrHoShadowError] = useState("");
  const [activeOcrHoShadowId, setActiveOcrHoShadowId] = useState("");
  const [ocrHoShadowDetail, setOcrHoShadowDetail] =
    useState<OcrHoShadowDetail | null>(null);
  const [ocrHoShadowDetailLoading, setOcrHoShadowDetailLoading] = useState(false);
  const [ocrHoShadowDetailError, setOcrHoShadowDetailError] = useState("");
  const [ocrHoShadowRefresh, setOcrHoShadowRefresh] = useState(0);
  const [groundTruthReview, setGroundTruthReview] =
    useState<CccdGroundTruthReviewSummary | null>(null);
  const [groundTruthReviewError, setGroundTruthReviewError] = useState("");
  const [activeGroundTruthId, setActiveGroundTruthId] = useState("");
  const [groundTruthReviewDocument, setGroundTruthReviewDocument] =
    useState<CccdGroundTruthReviewDocument | null>(null);
  const [groundTruthFields, setGroundTruthFields] = useState<
    Record<string, CccdGroundTruthField>
  >({});
  const [groundTruthAssertions, setGroundTruthAssertions] = useState({
    comparedWithImage: false,
    allTextChecked: false,
  });
  const [isSavingGroundTruth, setIsSavingGroundTruth] = useState(false);
  const [isLockingGroundTruth, setIsLockingGroundTruth] = useState(false);
  const [isEvaluatingGroundTruth, setIsEvaluatingGroundTruth] = useState(false);
  const [groundTruthEvaluation, setGroundTruthEvaluation] =
    useState<CccdGroundTruthEvaluation | null>(null);
  const [groundTruthEvaluationDetail, setGroundTruthEvaluationDetail] =
    useState<CccdGroundTruthEvaluationDetail | null>(null);
  const [groundTruthEvaluationDetailError, setGroundTruthEvaluationDetailError] =
    useState("");
  const [isLoadingGroundTruthEvaluationDetail, setIsLoadingGroundTruthEvaluationDetail] =
    useState(false);
  const groundTruthDocumentExcluded =
    groundTruthReviewDocument?.disposition === "OUT_OF_SCOPE_BACK";
  const [evidenceMode, setEvidenceMode] =
    useState<"overview" | "data29" | "data31-coverage" | "cccd" | "external-dataset" | "external-dataset-prediction" | "external-dataset-prediction-v13" | "ocr-ho-v2-shadow" | "ocr-ho-v2-diagnostic">(
      "data29",
    );
  const [evidenceInspectorView, setEvidenceInspectorView] =
    useState<"fields" | "json">("fields");
  const [activeCccdSessionId, setActiveCccdSessionId] = useState("");
  const [cccdEvidenceResult, setCccdEvidenceResult] =
    useState<UserResult | null>(null);
  const [cccdEvidenceReview, setCccdEvidenceReview] =
    useState<Phase10Review | null>(null);
  const [cccdEvidenceLoading, setCccdEvidenceLoading] = useState(false);
  const [cccdEvidenceError, setCccdEvidenceError] = useState("");
  const [viewProfile, setViewProfile] = useState<"phase7" | "baseline">("phase7");
  const [processingMode, setProcessingMode] =
    useState<"template" | "legacy">("template");
  const [ocrDocumentType, setOcrDocumentType] = useState<
    | "CV"
    | "EMPLOYMENT_CONTRACT"
    | "CONTRACT_APPENDIX"
    | "HR_DECISION"
    | "IDENTITY_CARD"
    | "CERTIFICATE"
  >("IDENTITY_CARD");
  const [supportedTemplates, setSupportedTemplates] =
    useState<SupportedTemplate[]>([]);
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [templateResult, setTemplateResult] =
    useState<TemplateProcessingResult | null>(null);
  const [camundaStatus, setCamundaStatus] = useState("");
  const [camundaCase, setCamundaCase] = useState<CamundaCaseStatus | null>(null);
  const [camundaQueue, setCamundaQueue] = useState<CamundaReviewTask[]>([]);
  const [camundaQueueStatus, setCamundaQueueStatus] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPreviewUrl, setUploadPreviewUrl] = useState("");
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

  useEffect(
    () => () => {
      if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl);
    },
    [uploadPreviewUrl],
  );

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

  const selectUploadFile = (file: File | null) => {
    setUploadFile(file);
    setUploadPreviewUrl(file ? URL.createObjectURL(file) : "");
    setUploadError("");
    setTemplateResult(null);
    setCamundaCase(null);
    setCamundaStatus("");
    setLoadedUserResult(null);
    setDeleteArmed(false);
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

  const refreshCamundaQueue = () => {
    fetch(`${API_BASE}/api/camunda/queue`)
      .then((response) => {
        if (!response.ok) throw new Error("Camunda queue unavailable");
        return response.json() as Promise<{ queue: CamundaReviewTask[] }>;
      })
      .then((payload) => {
        setCamundaQueue(payload.queue);
        setCamundaQueueStatus("");
      })
      .catch(() => setCamundaQueueStatus("Chưa kết nối được Camunda local."));
  };

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((response) => {
        if (!response.ok) throw new Error("offline");
        return response.json() as Promise<{ userUpload: RuntimeHealth }>;
      })
      .then((payload) => {
        setApiOnline(true);
        setRuntimeHealth(payload.userUpload);
      })
      .catch(() => {
        setApiOnline(false);
        setRuntimeHealth(null);
      });
    fetch(`${API_BASE}/api/templates`)
      .then((response) => {
        if (!response.ok) throw new Error("Template registry unavailable");
        return response.json();
      })
      .then((payload: { templates: SupportedTemplate[] }) =>
        setSupportedTemplates(payload.templates),
      )
      .catch(() => setSupportedTemplates([]));
    refreshUserSessions();
    refreshCamundaQueue();
    if (!SHOW_OCR_HO_SHADOW_UAT) return;
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
    if (!SHOW_GROUND_TRUTH_REVIEW) {
      return;
    }
    fetch(`${API_BASE}/cccd-heldout/review/summary`)
      .then((response) => {
        if (!response.ok) throw new Error("Ground Truth review unavailable");
        return response.json();
      })
      .then((payload: CccdGroundTruthReviewSummary) => {
        setGroundTruthReview(payload);
        setGroundTruthReviewError("");
        setActiveGroundTruthId((current) =>
          payload.documents.some((document) => document.documentId === current)
            ? current
            : payload.documents[0]?.documentId ?? "",
        );
      })
      .catch(() => {
        setGroundTruthReview(null);
        setGroundTruthReviewError(
          "Chưa kết nối được hàng đợi Ground Truth local-only.",
        );
      });
  }, []);

  useEffect(() => {
    if (!SHOW_OCR_HO_SHADOW_UAT) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear unavailable optional shadow data.
      setOcrHoShadow(null);
      return;
    }
    fetch(`${API_BASE}/ocr-ho-v2/shadow/summary`)
      .then((response) => {
        if (!response.ok) throw new Error("OCR-HO-V2 shadow UAT unavailable");
        return response.json() as Promise<OcrHoShadowSummary>;
      })
      .then((payload) => {
        setOcrHoShadow(payload);
        setOcrHoShadowError("");
        setActiveOcrHoShadowId((current) =>
          payload.documents.some((document) => document.documentId === current)
            ? current
            : payload.documents[0]?.documentId ?? "",
        );
      })
      .catch((fetchError) => {
        setOcrHoShadow(null);
        setOcrHoShadowError(
          fetchError instanceof Error
            ? fetchError.message
            : "Chưa kết nối được shadow UAT local.",
        );
      });
  }, [ocrHoShadowRefresh]);

  useEffect(() => {
    if (!SHOW_OCR_HO_SHADOW_UAT || !activeOcrHoShadowId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear stale selected shadow detail.
      setOcrHoShadowDetail(null);
      return;
    }
    let cancelled = false;
    setOcrHoShadowDetailLoading(true);
    setOcrHoShadowDetailError("");
    fetch(
      `${API_BASE}/ocr-ho-v2/shadow/document?id=${encodeURIComponent(
        activeOcrHoShadowId,
      )}&mode=detail`,
    )
      .then((response) => {
        if (!response.ok) throw new Error("Shadow UAT document unavailable");
        return response.json() as Promise<OcrHoShadowDetail>;
      })
      .then((payload) => {
        if (!cancelled) setOcrHoShadowDetail(payload);
      })
      .catch((fetchError) => {
        if (cancelled) return;
        setOcrHoShadowDetail(null);
        setOcrHoShadowDetailError(
          fetchError instanceof Error
            ? fetchError.message
            : "Không đọc được shadow evidence local.",
        );
      })
      .finally(() => {
        if (!cancelled) setOcrHoShadowDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeOcrHoShadowId, ocrHoShadowRefresh]);

  useEffect(() => {
    if (!SHOW_GROUND_TRUTH_REVIEW || !activeGroundTruthId) {
      // Clear dependent review state when the selected document is unavailable.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset state from the external review queue.
      setGroundTruthReviewDocument(null);
      setGroundTruthFields({});
      return;
    }
    let cancelled = false;
    fetch(
      `${API_BASE}/cccd-heldout/review/document?id=${encodeURIComponent(
        activeGroundTruthId,
      )}&mode=detail`,
    )
      .then((response) => {
        if (!response.ok) throw new Error("Ground Truth document unavailable");
        return response.json();
      })
      .then((payload: CccdGroundTruthReviewDocument) => {
        if (cancelled) return;
        setGroundTruthReviewDocument(payload);
        setGroundTruthFields(payload.fields);
        setGroundTruthAssertions(payload.verificationAssertions);
      })
      .catch(() => {
        if (!cancelled) {
          setGroundTruthReviewDocument(null);
          setGroundTruthReviewError("Không đọc được tài liệu Ground Truth local.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeGroundTruthId]);

  useEffect(() => {
    if (
      !activeGroundTruthId ||
      groundTruthReview?.evaluationStatus !== "COMPLETE"
    ) {
      // Clear stale evaluation output when the external status is not complete.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset state from the external evaluation queue.
      setGroundTruthEvaluationDetail(null);
      setGroundTruthEvaluationDetailError("");
      return;
    }
    let cancelled = false;
    setIsLoadingGroundTruthEvaluationDetail(true);
    fetch(
      `${API_BASE}/cccd-heldout/review/evaluation?id=${encodeURIComponent(
        activeGroundTruthId,
      )}`,
    )
      .then((response) => {
        if (!response.ok) throw new Error("Evaluation output unavailable");
        return response.json();
      })
      .then((payload: CccdGroundTruthEvaluationDetail) => {
        if (cancelled) return;
        setGroundTruthEvaluationDetail(payload);
        setGroundTruthEvaluationDetailError("");
      })
      .catch((error) => {
        if (cancelled) return;
        setGroundTruthEvaluationDetail(null);
        setGroundTruthEvaluationDetailError(
          error instanceof Error
            ? error.message
            : "Không đọc được output sau evaluate-once.",
        );
      })
      .finally(() => {
        if (!cancelled) setIsLoadingGroundTruthEvaluationDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeGroundTruthId, groundTruthReview?.evaluationStatus]);

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

  const refreshGroundTruthReview = async () => {
    const response = await fetch(`${API_BASE}/cccd-heldout/review/summary`);
    if (!response.ok) throw new Error("Ground Truth review unavailable");
    const payload = (await response.json()) as CccdGroundTruthReviewSummary;
    setGroundTruthReview(payload);
    setActiveGroundTruthId((current) =>
      payload.documents.some((document) => document.documentId === current)
        ? current
        : payload.documents[0]?.documentId ?? "",
    );
  };

  const setGroundTruthDisposition = async (
    disposition: "IN_SCOPE_FRONT" | "OUT_OF_SCOPE_BACK",
  ) => {
    if (
      !activeGroundTruthId ||
      !groundTruthReviewDocument ||
      groundTruthReview?.groundTruthStatus === "CONFIRMED"
    ) {
      return;
    }
    setGroundTruthReviewError("");
    try {
      const response = await fetch(
        `${API_BASE}/cccd-heldout/review/disposition?id=${encodeURIComponent(
          activeGroundTruthId,
        )}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            disposition,
            reason:
              disposition === "OUT_OF_SCOPE_BACK"
                ? "back_side_outside_front_schema"
                : "",
          }),
        },
      );
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        throw new Error(payload.error ?? "Không cập nhật phạm vi tài liệu");
      }
      await refreshGroundTruthReview();
    } catch (error) {
      setGroundTruthReviewError(
        error instanceof Error
          ? error.message
          : "Không cập nhật phạm vi tài liệu local.",
      );
    }
  };

  const saveGroundTruthReview = async () => {
    if (
      !activeGroundTruthId ||
      !groundTruthReviewDocument ||
      groundTruthDocumentExcluded ||
      isSavingGroundTruth
    ) {
      return;
    }
    setIsSavingGroundTruth(true);
    setGroundTruthReviewError("");
    try {
      const response = await fetch(
        `${API_BASE}/cccd-heldout/review/save?id=${encodeURIComponent(
          activeGroundTruthId,
        )}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fields: groundTruthFields,
            assertions: groundTruthAssertions,
          }),
        },
      );
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không lưu được Ground Truth");
      await refreshGroundTruthReview();
    } catch (error) {
      setGroundTruthReviewError(
        error instanceof Error ? error.message : "Không lưu được Ground Truth local.",
      );
    } finally {
      setIsSavingGroundTruth(false);
    }
  };

  const lockGroundTruthReview = async () => {
    if (!groundTruthReview?.canLock || isLockingGroundTruth) return;
    setIsLockingGroundTruth(true);
    setGroundTruthReviewError("");
    try {
      const response = await fetch(`${API_BASE}/cccd-heldout/review/lock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không khóa được Ground Truth");
      await refreshGroundTruthReview();
    } catch (error) {
      setGroundTruthReviewError(
        error instanceof Error ? error.message : "Không khóa được Ground Truth local.",
      );
    } finally {
      setIsLockingGroundTruth(false);
    }
  };

  const evaluateGroundTruthOnce = async () => {
    if (!groundTruthReview?.canEvaluate || isEvaluatingGroundTruth) return;
    setIsEvaluatingGroundTruth(true);
    setGroundTruthReviewError("");
    try {
      const response = await fetch(`${API_BASE}/cccd-heldout/review/evaluate`, {
        method: "POST",
      });
      const payload = (await response.json()) as CccdGroundTruthEvaluation & {
        error?: string;
      };
      if (!response.ok) throw new Error(payload.error ?? "Evaluate once thất bại");
      setGroundTruthEvaluation(payload);
      await refreshGroundTruthReview();
    } catch (error) {
      setGroundTruthReviewError(
        error instanceof Error ? error.message : "Evaluate once thất bại.",
      );
    } finally {
      setIsEvaluatingGroundTruth(false);
    }
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
      !/\.(docx|pdf|png|jpe?g)$/i.test(uploadFile.name)
    ) {
      setUploadError(
        "Template-first hiện hỗ trợ DOCX, PDF, PNG và JPG/JPEG theo từng mẫu tài liệu.",
      );
      return;
    }
    setIsUploading(true);
    setUploadError("");
    setLoadedUserResult(null);
    setTemplateResult(null);
    setCamundaCase(null);
    setCamundaStatus("");
    setDeleteArmed(false);
    const formData = new FormData();
    formData.append("file", uploadFile);
    if (processingMode === "legacy") {
      formData.append("documentType", ocrDocumentType);
    }
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
        const templateErrorMessages: Record<string, string> = {
          SUPPORTED_TEMPLATE_FORMAT_REQUIRED:
            "Định dạng này chưa được intake hỗ trợ. Dùng TXT, DOCX, PDF, XLSX, PPTX hoặc ảnh PNG/JPG/TIF/WEBP.",
          "Document does not match an approved template":
            "Chưa nhận diện được mẫu tài liệu. Tài liệu vẫn hợp lệ nhưng cần thêm template hoặc chuyển sang pipeline IDP tổng quát.",
          "Unsupported file type":
            "File hợp lệ nhưng parser local chưa hỗ trợ loại nội dung này.",
        };
        throw new Error(
          processingMode === "template"
            ? errorCode === "OCR_RUNTIME_UNAVAILABLE"
              ? "OCR local chưa sẵn sàng. Hãy cài runtime PaddleOCR rồi thử lại."
              : templateErrorMessages[errorCode] ??
                `Không xử lý được biểu mẫu: ${errorCode}`
            : `OCR local thất bại: ${errorCode}`,
        );
      }
      if (processingMode === "template") {
        const result = payload as TemplateProcessingResult;
        setTemplateResult(result);
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

  const startCamundaCase = async () => {
    const documentId = templateResult?.data.documentId;
    if (!documentId) return;
    setCamundaStatus("Đang tạo case Camunda local...");
    try {
      const response = await fetch(`${API_BASE}/api/camunda/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ documentId }),
      });
      const payload = (await response.json()) as {
        error?: string;
        tasklistUrl?: string;
        processInstanceId?: string;
        applicationId?: string;
      };
      if (!response.ok) throw new Error(payload.error ?? "Không thể tạo case Camunda");
      if (!payload.processInstanceId) throw new Error("Camunda không trả process instance id");
      setCamundaCase({
        processInstanceId: payload.processInstanceId,
        applicationId: payload.applicationId ?? null,
        documentType: templateResult.documentType,
        state: "PROCESSING",
        taskId: null,
        taskName: null,
        incidentCount: 0,
        tasklistUrl: payload.tasklistUrl ?? "http://localhost:8080/camunda/app/tasklist/default/",
      });
      setCamundaStatus("Đã tạo case. Mở Camunda Tasklist để xác nhận dữ liệu.");
      refreshCamundaQueue();
      if (payload.tasklistUrl) window.open(payload.tasklistUrl, "_blank", "noopener");
    } catch (error) {
      setCamundaStatus(error instanceof Error ? error.message : "Không thể tạo case Camunda");
    }
  };

  const refreshCamundaCase = async () => {
    if (!camundaCase) return;
    setCamundaStatus("Đang cập nhật trạng thái Camunda local...");
    try {
      const response = await fetch(
        `${API_BASE}/api/camunda/case?id=${encodeURIComponent(camundaCase.processInstanceId)}`,
      );
      const payload = (await response.json()) as CamundaCaseStatus & { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không đọc được trạng thái Camunda");
      setCamundaCase(payload);
      setCamundaStatus("Đã cập nhật trạng thái Camunda local.");
      refreshCamundaQueue();
    } catch (error) {
      setCamundaStatus(error instanceof Error ? error.message : "Không đọc được trạng thái Camunda");
    }
  };

  const inspectCamundaDocument = async (documentId: string) => {
    setCamundaQueueStatus("Đang mở bản gốc và JSON local...");
    try {
      const response = await fetch(
        `${API_BASE}/api/documents/result?id=${encodeURIComponent(documentId)}`,
      );
      if (!response.ok) throw new Error("Không tìm thấy session local của case này");
      setUploadFile(null);
      setUploadPreviewUrl("");
      setLoadedUserResult(null);
      setTemplateResult((await response.json()) as TemplateProcessingResult);
      setProcessingMode("template");
      setCamundaQueueStatus("");
      window.location.hash = "upload";
    } catch (error) {
      setCamundaQueueStatus(
        error instanceof Error ? error.message : "Không thể mở dữ liệu local",
      );
    }
  };

  const completeCamundaReview = async (
    task: CamundaReviewTask,
    decision: string,
  ) => {
    setCamundaQueueStatus("Đang gửi quyết định sang Camunda local...");
    try {
      const response = await fetch(`${API_BASE}/api/camunda/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId: task.taskId, role: task.role, decision }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không thể hoàn thành task");
      setCamundaQueueStatus("Đã ghi nhận. Camunda đang điều phối bước tiếp theo.");
      refreshCamundaQueue();
    } catch (error) {
      setCamundaQueueStatus(error instanceof Error ? error.message : "Không thể hoàn thành task");
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
      selectUploadFile(null);
      setDeleteArmed(false);
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
      selectUploadFile(null);
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
  const cccdEvidenceDocuments = useMemo(
    () =>
      (groundTruthReview?.documents ?? []).filter(
        (document) => document.disposition === "IN_SCOPE_FRONT",
      ),
    [groundTruthReview],
  );
  const activeCccdEvidenceDocument =
    cccdEvidenceDocuments.find(
      (document) => document.documentId === activeGroundTruthId,
    ) ??
    cccdEvidenceDocuments[0] ??
    null;
  const cccdEvidenceMetrics =
    groundTruthReview?.evaluation?.metrics?.phase11_6 ?? null;
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
        identityCard && cccdEvidenceResult.phase11?.version === "1.1.0"
          ? "VIETNAM_CITIZEN_ID_FRONT / OCR-HO-V2 v1.1"
          : cccdEvidenceResult.phase11_5
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
  const unifiedIdp = userResult?.phase15 ?? userResult?.phase12;
  const templateSourceUrl = templateResult
    ? `${API_BASE}/api/documents/source?id=${encodeURIComponent(
        templateResult.data.documentId,
      )}`
    : "";
  const documentPreviewUrl = uploadPreviewUrl || templateSourceUrl;
  const documentPreviewFilename =
    uploadFile?.name ??
    (typeof templateResult?.data.sourceFile === "string"
      ? templateResult.data.sourceFile
      : "");

  return (
    <main className="operations-site">
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="Về đầu trang">
          <span className="brand-mark">V</span>
          <span>VinHRIS</span><small>HCNS</small>
        </a>
        <nav aria-label="Điều hướng chính">
          <a href="#overview">Tổng quan</a>
          <a href="#upload">Tiếp nhận</a>
          <a href="#roles">Hàng đợi</a>
          <a href="#explorer">Evidence</a>
          <a
            className="camunda-link"
            href="http://localhost:8080/camunda/app/tasklist/default/"
            rel="noreferrer"
            target="_blank"
          >
            Camunda <span aria-hidden="true">↗</span>
          </a>
        </nav>
        <span className={`live ${apiOnline ? "online" : ""}`}>
          <i />
          {apiOnline ? "Hệ thống sẵn sàng" : "Chế độ xem dữ liệu"}
        </span>
      </header>

      <section className="hero" id="overview">
        <div className="hero-copy">
          <p className="eyebrow">Nền tảng xử lý hồ sơ HCNS</p>
          <h1>
            Hồ sơ vào một chỗ.
            <span> Quy trình đi đúng nơi.</span>
          </h1>
          <p className="hero-lead">
            Tiếp nhận, trích xuất và chuyển hồ sơ đến đúng người kiểm tra trong một luồng local an toàn.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#upload">
              Tiếp nhận hồ sơ
            </a>
            <a className="text-button" href="#workflow">
              Xem quy trình <span>→</span>
            </a>
          </div>
        </div>
        <figure className="hero-product" aria-label="Không gian xử lý tài liệu HCNS local">
          <div
            className="hero-product-frame hero-workflow-visual"
            data-testid="product-showcase"
          >
            <img
              alt="Nhân sự kiểm tra tài liệu trong không gian làm việc số"
              src="/assets/hr-document-intelligence-context.webp"
            />
            <div className="hero-image-note">
              <span>LOCAL ONLY</span>
              <strong>Template-first + Human Review</strong>
            </div>
          </div>
          <figcaption>
            File và kết quả được giữ trong private storage của môi trường local.
          </figcaption>
        </figure>
      </section>

      <section className="section product-section" id="platform">
        <div className="platform-intro">
          <p className="section-eyebrow">Một nền tảng thống nhất</p>
          <h2>Từ file đầu vào đến quyết định có kiểm soát.</h2>
          <p>
            Mỗi bước dùng đúng parser, lưu đúng evidence và dừng lại cho con người xác nhận khi cần.
          </p>
        </div>
        <ol className="platform-rail" aria-label="Năm lớp của nền tảng xử lý hồ sơ">
          <li><span>01</span><strong>Intake</strong><small>DOCX, PDF và ảnh</small></li>
          <li><span>02</span><strong>OCR</strong><small>Native trước, OCR khi cần</small></li>
          <li><span>03</span><strong>Template</strong><small>Parser có version</small></li>
          <li><span>04</span><strong>Human Review</strong><small>Xác nhận trường nhạy cảm</small></li>
          <li><span>05</span><strong>Camunda</strong><small>Điều phối local shadow</small></li>
        </ol>
      </section>

      <section className="section document-family-section" id="document-types">
        <div className="section-heading">
          <div>
            <p className="section-eyebrow">Ba nhóm tài liệu hiện có</p>
            <h2>Ưu tiên độ tin cậy trước khi mở rộng.</h2>
          </div>
          <p>Chỉ số dưới đây thuộc DATA-29 development corpus và không đại diện cho chất lượng production.</p>
        </div>
        <div className="document-family-layout">
          <article className="document-family-primary">
            <span className="document-index">01 / Contract</span>
            <div>
              <h3>Hợp đồng lao động</h3>
              <p>Template extraction đã được đối chiếu. Camunda local shadow đang chờ hoàn tất case Contract đầu tiên.</p>
            </div>
            <strong>42 / 42 exact</strong>
            <small>3 tài liệu development</small>
          </article>
          <div className="document-family-list">
            <article>
              <span className="document-index">02 / CV</span>
              <h3>Hồ sơ ứng viên</h3>
              <p>45 / 50 exact, 50 / 50 accepted</p>
              <small>5 tài liệu development</small>
            </article>
            <article>
              <span className="document-index">03 / IELTS</span>
              <h3>Chứng chỉ IELTS</h3>
              <p>20 / 20 exact và accepted</p>
              <small>4 tài liệu development</small>
            </article>
          </div>
        </div>
      </section>

      <section className="section quality-overview-section" id="quality">
        <div className="quality-copy">
          <p className="section-eyebrow">Quality evidence</p>
          <h2>Con số có nguồn. Giới hạn được nói rõ.</h2>
          <p>
            DATA-29 khóa đúng 12 tài liệu development: 3 Contract, 5 CV và 4 IELTS. Ground Truth không được sửa trong lần thiết kế này.
          </p>
          <a className="text-button" href="#explorer">Mở Evidence <span>→</span></a>
        </div>
        <dl className="quality-numbers">
          <div><dt>Exact match</dt><dd>107<span>/112</span></dd></div>
          <div><dt>Accepted</dt><dd>112<span>/112</span></dd></div>
          <div className="quality-gate"><dt>Promotion gate</dt><dd>HOLD</dd><small>Chưa phải bằng chứng production</small></div>
        </dl>
      </section>

      <section className="section workflow-section" id="workflow">
        <div className="workflow-heading">
          <p className="section-eyebrow">Quy trình local shadow</p>
          <h2>Một hồ sơ, một đường đi có thể kiểm tra.</h2>
          <p>Camunda chỉ nhận reference và metadata an toàn. Nội dung file không đi vào process variables.</p>
        </div>
        <ol className="workflow-timeline" aria-label="Quy trình xử lý hồ sơ từ upload tới hoàn tất">
          <li><span>01</span><div><strong>Upload local</strong><small>Kiểm tra định dạng và an toàn file</small></div></li>
          <li><span>02</span><div><strong>Đọc tài liệu</strong><small>Native parser hoặc OCR theo source</small></div></li>
          <li><span>03</span><div><strong>Trích xuất</strong><small>Template và parser versioned</small></div></li>
          <li><span>04</span><div><strong>Human Review</strong><small>Người dùng xác nhận kết quả</small></div></li>
          <li><span>05</span><div><strong>Camunda hoàn tất</strong><small>Audit local, không side effect thật</small></div></li>
        </ol>
      </section>

      <RoleReviewQueue
        tasks={camundaQueue}
        onInspect={inspectCamundaDocument}
        onReview={completeCamundaReview}
      />
      {camundaQueueStatus ? <p className="camunda-queue-status">{camundaQueueStatus}</p> : null}

      <section className="section upload-section" id="upload">
        <div className="section-heading">
          <div>
            <p className="eyebrow">TIẾP NHẬN HỒ SƠ</p>
            <h2>Chọn tài liệu cần xử lý</h2>
          </div>
          <p>
            Tệp và kết quả xử lý được lưu trong phiên làm việc nội bộ. Dữ liệu không được
            gửi lên dịch vụ bên ngoài.
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
              {showLegacyUpload ? (
                <div
                  className="upload-mode-switch"
                  role="tablist"
                  aria-label="Chế độ xử lý"
                >
                  <button
                    aria-selected={processingMode === "template"}
                    className={processingMode === "template" ? "active" : ""}
                    onClick={() => {
                      setProcessingMode("template");
                      selectUploadFile(null);
                      setLoadedUserResult(null);
                      setDeleteArmed(false);
                    }}
                    role="tab"
                    type="button"
                  >
                    <strong>Biểu mẫu HCNS</strong>
                    <span>DOCX/PDF theo mẫu đã cấu hình</span>
                  </button>
                  <button
                    aria-selected={processingMode === "legacy"}
                    className={processingMode === "legacy" ? "active" : ""}
                    onClick={() => {
                      setProcessingMode("legacy");
                      selectUploadFile(null);
                      setTemplateResult(null);
                      setDeleteArmed(false);
                    }}
                    role="tab"
                    type="button"
                  >
                    <strong>OCR / IDP local</strong>
                    <span>CV, hợp đồng, quyết định, CCCD, chứng chỉ</span>
                  </button>
                </div>
              ) : null}

              <div className="upload-intro">
                <span>MỘT ĐẦU VÀO · TỰ ĐỘNG CHỌN PIPELINE</span>
                <h3>Tải tài liệu HCNS</h3>
                <p>
                  Chọn tài liệu HCNS. Hệ thống tự nhận dạng định dạng, ưu tiên
                  native parser cho tài liệu có text và OCR local cho ảnh/PDF scan.
                </p>
                <small>{supportedTemplates.length || 2} biểu mẫu đang hỗ trợ</small>
              </div>
              {processingMode === "legacy" ? (
                <label className="upload-scope-select">
                  <span>LOẠI TÀI LIỆU SCAN</span>
                  <select
                    value={ocrDocumentType}
                    onChange={(event) =>
                      setOcrDocumentType(
                        event.target.value as
                          | "CV"
                          | "EMPLOYMENT_CONTRACT"
                          | "CONTRACT_APPENDIX"
                          | "HR_DECISION"
                          | "IDENTITY_CARD"
                          | "CERTIFICATE",
                      )
                    }
                  >
                    <option value="CV">CV / hồ sơ ứng viên</option>
                    <option value="EMPLOYMENT_CONTRACT">Hợp đồng lao động</option>
                    <option value="CONTRACT_APPENDIX">Phụ lục hợp đồng</option>
                    <option value="HR_DECISION">Quyết định nhân sự</option>
                    <option value="IDENTITY_CARD">CCCD / Identity card</option>
                    <option value="CERTIFICATE">Certificate / IELTS</option>
                  </select>
                </label>
              ) : null}

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
                  if (file) selectUploadFile(file);
                }}
              >
                <input
                  type="file"
                  data-testid="local-document-input"
                  accept={
                    processingMode === "template"
                      ? ".docx,.pdf,.png,.jpg,.jpeg"
                      : ".png,.jpg,.jpeg,.pdf,.docx,.xlsx"
                  }
                  onChange={(event) =>
                    selectUploadFile(event.target.files?.[0] ?? null)
                  }
                />
                <span className="upload-icon">＋</span>
                <strong>
                  {uploadFile ? uploadFile.name : "Kéo thả hoặc chọn tài liệu"}
                </strong>
                <p>
                  {uploadFile
                    ? `${(uploadFile.size / 1024 / 1024).toFixed(2)} MB`
                    : processingMode === "template"
                      ? "CV/Hợp đồng: DOCX, PDF · IELTS/CCCD: PDF, PNG, JPG/JPEG"
                      : "Ảnh/PDF scan: chọn đúng loại tài liệu; DOCX/XLSX/PDF có text: native parser"}
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
                    ? "Đang đọc và nhận diện tài liệu…"
                    : "Đang OCR local… có thể mất vài phút"
                  : processingMode === "template"
                    ? "Trích xuất tài liệu"
                    : "Phân tích bằng OCR / IDP"}
              </button>
              {uploadError && <div className="upload-error">{uploadError}</div>}
            </form>

            {showLegacyUpload && processingMode === "legacy" && (
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

          <div className="upload-workspace">
            <TemplateDocumentPreview
              filename={documentPreviewFilename}
              previewUrl={documentPreviewUrl}
              result={templateResult}
            />
            <div className="template-output-pane">
              {!userResult && !templateResult && !isUploading && (
                <div className="result-placeholder">
                  <span>JSON</span>
                  <h3>Kết quả sẽ xuất hiện tại đây</h3>
                  <p>
                    Trường dữ liệu, cảnh báo validation và JSON chuẩn sẽ hiển
                    thị cạnh bản xem trước của tài liệu.
                  </p>
                </div>
              )}
              {isUploading && (
                <div className="result-placeholder processing">
                  <i />
                  <h3>
                    {processingMode === "template"
                      ? "Đang nhận diện và cấu trúc hóa tài liệu"
                      : "Đang nạp model và đọc tài liệu"}
                  </h3>
                  <p>
                    {processingMode === "template"
                      ? "DOCX/PDF native được đọc trực tiếp; ảnh scan được chuyển qua OCR local."
                      : "Lần đầu có thể chậm hơn. Không đóng localhost trong khi xử lý."}
                  </p>
                </div>
              )}
              {templateResult && (
                <TemplateResultPanel
                  camundaCase={camundaCase}
                  deleteArmed={deleteArmed}
                  filename={documentPreviewFilename || "Tài liệu HCNS"}
                  onDelete={deleteTemplateSession}
                  onStartCamunda={startCamundaCase}
                  onRefreshCamunda={refreshCamundaCase}
                  camundaStatus={camundaStatus}
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
                      <span>OCR-HO-V2 / CCCD</span>
                      <strong>
                        v{phase11Label(userResult)} · {userResult.phase11.status}
                      </strong>
                      <small>
                        fixed 0° · scope {userResult.phase11.evaluationScope ?? "DEVELOPMENT_ONLY"} · xoay{" "}
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
        </div>
      </section>

      <section className="section" id="phases" data-testid="runtime-system-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">SYSTEM / ALGORITHM VERSION</p>
            <h2>Pipeline đang thực sự chạy</h2>
          </div>
          <p>
            Thông tin được đọc trực tiếp từ runtime và Template Registry, không
            suy ra từ benchmark hoặc tên file thuật toán.
          </p>
        </div>
        <div className="phase-grid" data-testid="runtime-pipeline-grid">
          <article className="phase-card">
            <div className="phase-top">
              <span>RUN</span>
              <b>{runtimeHealth?.backendAvailable ? "Available" : "Unavailable"}</b>
            </div>
            <h3>{runtimeHealth?.runtimeProfile ?? "Chưa kết nối runtime"}</h3>
            <p>Luồng sản phẩm mặc định dùng Template-first và luôn giữ Human Review.</p>
            <small>
              modelLoaded={String(runtimeHealth?.templateOcrModelLoaded ?? false)}
            </small>
          </article>
          <article className="phase-card">
            <div className="phase-top">
              <span>OCR</span>
              <b>{runtimeHealth?.backendAvailable ? "Active" : "Check runtime"}</b>
            </div>
            <h3>{runtimeHealth?.templateOcrBackend ?? "Chưa xác định"}</h3>
            <p>{runtimeHealth?.templateOcrProfile ?? "Chưa có OCR profile"}</p>
            <small>Paddle chỉ được dùng khi chọn rollback rõ ràng.</small>
          </article>
          {(runtimeHealth?.pipelines ?? []).map((pipeline, index) => (
            <article className="phase-card" key={pipeline.templateId}>
              <div className="phase-top">
                <span>{String(index + 1).padStart(2, "0")}</span>
                <b>{pipeline.lifecycle}</b>
              </div>
              <h3>{pipeline.documentType}</h3>
              <p>{pipeline.templateId} · template {pipeline.templateVersion}</p>
              <small>
                {pipeline.parserId} · {pipeline.parserVersion} · {pipeline.supportedFileTypes.join(", ")}
              </small>
            </article>
          ))}
        </div>
      </section>

      {SHOW_LEGACY_UPLOAD ? (
      <section className="section" id="legacy-recognition-policy">
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
      ) : null}

      {SHOW_GROUND_TRUTH_REVIEW ? (
        <section className="section ground-truth-review-section" id="ground-truth-review">
          <div className="section-heading">
            <div>
              <p className="eyebrow">LOCAL GROUND TRUTH REVIEW · CCCD</p>
              <h2>Xác nhận ảnh gốc trước evaluate-once</h2>
            </div>
            <p>
              Prediction vẫn bị ẩn. Bạn chỉ đối chiếu ảnh gốc, nhập giá trị nhìn thấy
              hoặc đánh dấu không có, rồi khóa bộ Ground Truth local.
            </p>
          </div>
          {groundTruthReviewError ? (
            <div className="ground-truth-review-error">{groundTruthReviewError}</div>
          ) : null}
          <div className="ground-truth-review-toolbar">
            <span>
              {groundTruthReview?.documentCount ?? 0} ảnh vào metric · {groundTruthReview?.excludedDocumentCount ?? 0} ảnh loại · {groundTruthReview?.fieldCount ?? 0} field/ảnh
            </span>
            <strong>
              {groundTruthReview?.groundTruthStatus ?? "CHƯA KẾT NỐI"}
            </strong>
            <span>
              {groundTruthReview?.evaluationStatus === "COMPLETE"
                ? "Evaluate once đã chạy"
                : "Prediction hidden · local-only"}
            </span>
          </div>
          <div className="ground-truth-review-grid">
            <div className="ground-truth-review-list" role="list">
              {(groundTruthReview?.documents ?? []).map((document) => (
                <button
                  key={document.documentId}
                  className={document.documentId === activeGroundTruthId ? "active" : ""}
                  onClick={() => setActiveGroundTruthId(document.documentId)}
                  role="listitem"
                  type="button"
                >
                  <span>{document.documentId}</span>
                  <strong>{document.sourceFile}</strong>
                  <small>
                    {document.disposition === "OUT_OF_SCOPE_BACK"
                      ? "OUT_OF_SCOPE_BACK · không tính metric"
                      : `${document.reviewedFieldCount}/${document.fieldCount} field · ${document.reviewStatus}`}
                  </small>
                </button>
              ))}
            </div>
            <div className="ground-truth-review-source">
              {groundTruthReviewDocument?.previewAvailable ? (
                <img
                  src={`${API_BASE}/cccd-heldout/review/document?id=${encodeURIComponent(
                    activeGroundTruthId,
                  )}&mode=preview`}
                  alt={`Ảnh CCCD ${activeGroundTruthId}`}
                  data-testid="ground-truth-source-preview"
                />
              ) : (
                <div className="native-heldout-file">
                  <span>LOCAL</span>
                  <strong>Ảnh nguồn chưa sẵn sàng</strong>
                </div>
              )}
              <div className="heldout-preview-actions">
                <div>
                  <strong>{groundTruthReviewDocument?.documentId ?? "—"}</strong>
                  <span>{groundTruthReviewDocument?.sourceFile ?? "Chọn tài liệu"}</span>
                </div>
              </div>
            </div>
            <div className="ground-truth-review-form">
              <div className="ground-truth-form-heading">
                <strong>Ground Truth theo field</strong>
                <span>Không hiển thị prediction trong màn hình này.</span>
              </div>
              {groundTruthDocumentExcluded ? (
                <div className="ground-truth-excluded-note">
                  <strong>OUT_OF_SCOPE_BACK</strong>
                  <span>
                    Ảnh mặt sau không thuộc schema CCCD mặt trước và không đưa vào metric.
                  </span>
                </div>
              ) : null}
              <div className="ground-truth-disposition-actions">
                <span>
                  Phạm vi: {groundTruthDocumentExcluded ? "loại khỏi metric" : "CCCD mặt trước"}
                </span>
                <button
                  className="secondary-action"
                  type="button"
                  onClick={() =>
                    setGroundTruthDisposition(
                      groundTruthDocumentExcluded
                        ? "IN_SCOPE_FRONT"
                        : "OUT_OF_SCOPE_BACK",
                    )
                  }
                  disabled={groundTruthReview?.groundTruthStatus === "CONFIRMED"}
                >
                  {groundTruthDocumentExcluded
                    ? "Đưa lại vào metric"
                    : "Loại ảnh mặt sau"}
                </button>
              </div>
              <div className="identity-ground-truth-grid">
                {Object.keys(identityFieldLabels).map((field) => {
                  const current = groundTruthFields[field] ?? {
                    value: "",
                    notPresent: false,
                  };
                  return (
                    <label key={field}>
                      <span>{identityFieldLabels[field]}</span>
                      <input
                        value={current.notPresent ? "" : current.value}
                        disabled={
                          groundTruthDocumentExcluded ||
                          groundTruthReview?.groundTruthStatus === "CONFIRMED"
                        }
                        onChange={(event) =>
                          setGroundTruthFields((previous) => ({
                            ...previous,
                            [field]: {
                              value: event.target.value,
                              notPresent: false,
                            },
                          }))
                        }
                        spellCheck
                      />
                      <small>
                        <input
                          type="checkbox"
                          checked={current.notPresent}
                          disabled={
                            groundTruthDocumentExcluded ||
                            groundTruthReview?.groundTruthStatus === "CONFIRMED"
                          }
                          onChange={(event) =>
                            setGroundTruthFields((previous) => ({
                              ...previous,
                              [field]: {
                                value: "",
                                notPresent: event.target.checked,
                              },
                            }))
                          }
                        />
                        Không có trên ảnh
                      </small>
                    </label>
                  );
                })}
              </div>
              <div className="review-assertions">
                <label>
                  <input
                    type="checkbox"
                    checked={groundTruthAssertions.comparedWithImage}
                    disabled={
                      groundTruthDocumentExcluded ||
                      groundTruthReview?.groundTruthStatus === "CONFIRMED"
                    }
                    onChange={(event) =>
                      setGroundTruthAssertions((current) => ({
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
                    checked={groundTruthAssertions.allTextChecked}
                    disabled={
                      groundTruthDocumentExcluded ||
                      groundTruthReview?.groundTruthStatus === "CONFIRMED"
                    }
                    onChange={(event) =>
                      setGroundTruthAssertions((current) => ({
                        ...current,
                        allTextChecked: event.target.checked,
                      }))
                    }
                  />
                  Tôi đã kiểm tra đủ chữ, dấu, số và field không có
                </label>
              </div>
              <div className="ground-truth-review-actions">
                <button
                  className="save-review"
                  type="button"
                  onClick={saveGroundTruthReview}
                  disabled={
                    isSavingGroundTruth ||
                    groundTruthDocumentExcluded ||
                    groundTruthReview?.groundTruthStatus === "CONFIRMED" ||
                    !groundTruthAssertions.comparedWithImage ||
                    !groundTruthAssertions.allTextChecked
                  }
                >
                  {isSavingGroundTruth ? "Đang lưu…" : "Lưu tài liệu đã review"}
                </button>
                <button
                  className="challenger-ready"
                  type="button"
                  onClick={lockGroundTruthReview}
                  disabled={
                    isLockingGroundTruth ||
                    !groundTruthReview?.canLock ||
                    groundTruthReview?.groundTruthStatus === "CONFIRMED"
                  }
                >
                  {isLockingGroundTruth ? "Đang khóa…" : "Khóa Ground Truth"}
                </button>
                <button
                  className="save-review"
                  type="button"
                  onClick={evaluateGroundTruthOnce}
                  disabled={isEvaluatingGroundTruth || !groundTruthReview?.canEvaluate}
                >
                  {isEvaluatingGroundTruth ? "Đang evaluate…" : "Evaluate once"}
                </button>
              </div>
              {groundTruthEvaluation ? (
                <div className="ground-truth-evaluation-result" data-testid="ground-truth-evaluation-result">
                  <strong>{groundTruthEvaluation.promotionGate.status}</strong>
                  <span>
                    {groundTruthEvaluation.documentCount} tài liệu · strict exact không chứa PII
                  </span>
                  <small>
                    {groundTruthEvaluation.promotionGate.exactRegressionCount ?? 0} regression · quyết định giữ/promotion theo gate
                  </small>
                </div>
              ) : null}
              {groundTruthReview?.evaluationStatus === "COMPLETE" ? (
                <CccdEvaluationInspector
                  detail={groundTruthEvaluationDetail}
                  loading={isLoadingGroundTruthEvaluationDetail}
                  error={groundTruthEvaluationDetailError}
                />
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <section className="section explorer-section" id="explorer">
        <div className="section-heading">
          <div>
            <p className="eyebrow">LOCAL DOCUMENT EVIDENCE</p>
            <h2>Tài liệu gắn trực tiếp với metric</h2>
          </div>
          <p>
            DATA-29 mở đúng 12 source đã tạo metric development và giữ nguyên
            Prediction, Ground Truth cùng report đã khóa.
          </p>
        </div>
        <div className="evidence-switch" role="tablist">
          <button
            className={evidenceMode === "data29" ? "active" : ""}
            onClick={() => setEvidenceMode("data29")}
            role="tab"
            aria-selected={evidenceMode === "data29"}
          >
            DATA-29 · 12 tài liệu metric · 3 Contract · 5 CV · 4 IELTS
          </button>
          {SHOW_DATA31_COVERAGE_REVIEW ? (
            <button
              className={evidenceMode === "data31-coverage" ? "active" : ""}
              onClick={() => setEvidenceMode("data31-coverage")}
              role="tab"
              aria-selected={evidenceMode === "data31-coverage"}
            >
              DATA-31 · Bổ sung GT còn thiếu / semantics IELTS
            </button>
          ) : null}
          {SHOW_OCR_HO_DIAGNOSTIC_GT ? (
            <button
              className={evidenceMode === "ocr-ho-v2-diagnostic" ? "active" : ""}
              onClick={() => setEvidenceMode("ocr-ho-v2-diagnostic")}
              role="tab"
              aria-selected={evidenceMode === "ocr-ho-v2-diagnostic"}
            >
              OCR-HO-V2 v11.10.0 · Prediction-blind GT
            </button>
          ) : null}
          {SHOW_OCR_HO_SHADOW_UAT ? (
            <button
              className={evidenceMode === "ocr-ho-v2-shadow" ? "active" : ""}
              onClick={() => setEvidenceMode("ocr-ho-v2-shadow")}
              role="tab"
              aria-selected={evidenceMode === "ocr-ho-v2-shadow"}
            >
              OCR-HO-V2 v{ocrHoShadow?.candidateVersion ?? "11.10.0"} · Shadow UAT
            </button>
          ) : null}
          {SHOW_GROUND_TRUTH_REVIEW ? (
          <button
            className={evidenceMode === "cccd" ? "active" : ""}
            onClick={() => setEvidenceMode("cccd")}
            role="tab"
            aria-selected={evidenceMode === "cccd"}
          >
            {groundTruthReview?.documentCount ?? 0} CCCD mới đã Ground Truth
          </button>
          ) : null}
          {SHOW_LEGACY_EXPLORER_TABS && SHOW_EXTERNAL_DATASET_REVIEW ? (
            <button
              className={evidenceMode === "external-dataset" ? "active" : ""}
              onClick={() => setEvidenceMode("external-dataset")}
              role="tab"
              aria-selected={evidenceMode === "external-dataset"}
            >
              DATA-08 · 4 contract case review
            </button>
          ) : null}
          {SHOW_LEGACY_EXPLORER_TABS && SHOW_EXTERNAL_DATASET_REVIEW ? (
            <>
          <button
            className={evidenceMode === "external-dataset-prediction" ? "active" : ""}
            onClick={() => setEvidenceMode("external-dataset-prediction")}
            role="tab"
            aria-selected={evidenceMode === "external-dataset-prediction"}
          >
           DATA-12 · Prediction + GT
           </button>
            <button
              className={evidenceMode === "external-dataset-prediction-v13" ? "active" : ""}
            onClick={() => setEvidenceMode("external-dataset-prediction-v13")}
            role="tab"
            aria-selected={evidenceMode === "external-dataset-prediction-v13"}
          >
            DATA-13 · OCR scope
            </button>
            </>
            ) : null}
        </div>
        {evidenceMode === "data29" ? (
          <ExternalDatasetPrediction version="data29" />
        ) : SHOW_DATA31_COVERAGE_REVIEW && evidenceMode === "data31-coverage" ? (
          <ExternalDatasetReview data31 />
        ) : evidenceMode === "overview" ? (
          <LocalEvidenceOverview
            onOpen={(mode) => setEvidenceMode(mode)}
          />
        ) : SHOW_OCR_HO_DIAGNOSTIC_GT && evidenceMode === "ocr-ho-v2-diagnostic" ? (
          <OcrHoDiagnostic />
        ) : SHOW_OCR_HO_SHADOW_UAT && evidenceMode === "ocr-ho-v2-shadow" ? (
          <div className="heldout-evidence-grid shadow-uat-grid">
            <div className="heldout-document-list" role="list">
              {(ocrHoShadow?.documents ?? []).map((document) => (
                <button
                  className={
                    document.documentId === activeOcrHoShadowId ? "active" : ""
                  }
                  key={document.documentId}
                  onClick={() => setActiveOcrHoShadowId(document.documentId)}
                  role="listitem"
                >
                  <span>DEV-{String(document.documentIndex).padStart(2, "0")}</span>
                  <strong>{document.sourceFile}</strong>
                  <small>
                    {document.reviewDecision} · {document.sourceFormat} · v
                    {ocrHoShadow?.candidateVersion ?? "11.10.0"}
                  </small>
                </button>
              ))}
              {!ocrHoShadow?.documents.length ? (
                <div className="evidence-inspector-state">
                  {ocrHoShadowError || "Chưa có development shadow artifact."}
                </div>
              ) : null}
            </div>
            <div className="heldout-preview">
              {activeOcrHoShadowId ? (
                <img
                  src={`${API_BASE}/ocr-ho-v2/shadow/document?id=${encodeURIComponent(
                    activeOcrHoShadowId,
                  )}&mode=preview`}
                  alt={`Ảnh nguồn shadow UAT ${activeOcrHoShadowId}`}
                  data-testid="ocr-ho-shadow-source-preview"
                />
              ) : (
                <div className="native-heldout-file">
                  <strong>Chưa có ảnh development shadow</strong>
                </div>
              )}
              {ocrHoShadowDetail ? (
                <div className="heldout-preview-actions">
                  <div>
                    <strong>{ocrHoShadowDetail.sourceFile}</strong>
                    <span>
                      Baseline Phase 11.5 → candidate v
                      {ocrHoShadowDetail.candidateVersion ?? "11.10.0"} · Ground Truth không nạp
                    </span>
                  </div>
                  <a
                    href={`${API_BASE}/ocr-ho-v2/shadow/document?id=${encodeURIComponent(
                      activeOcrHoShadowId,
                    )}&mode=source`}
                  >
                    Mở / tải ảnh nguồn
                  </a>
                </div>
              ) : null}
            </div>
            <OcrHoShadowInspector
              detail={ocrHoShadowDetail}
              loading={ocrHoShadowDetailLoading}
              error={ocrHoShadowDetailError}
              onReviewed={() => setOcrHoShadowRefresh((value) => value + 1)}
            />
          </div>
        ) : SHOW_EXTERNAL_DATASET_REVIEW && evidenceMode === "external-dataset-prediction" ? (
          <ExternalDatasetPrediction />
        ) : SHOW_EXTERNAL_DATASET_REVIEW && evidenceMode === "external-dataset-prediction-v13" ? (
          <ExternalDatasetPrediction version="data13" />
        ) : SHOW_EXTERNAL_DATASET_REVIEW && evidenceMode === "external-dataset" ? (
          <ExternalDatasetReview />
        ) : SHOW_GROUND_TRUTH_REVIEW && evidenceMode === "cccd" ? (
          <div className="heldout-evidence-grid">
            <div className="heldout-document-list" role="list">
              {cccdEvidenceDocuments.map((document) => (
                <button
                  className={
                    document.documentId === activeGroundTruthId ? "active" : ""
                  }
                  key={document.documentId}
                  onClick={() => setActiveGroundTruthId(document.documentId)}
                  role="listitem"
                >
                  <span>{document.documentId}</span>
                  <strong>CCCD mặt trước · Phase 11.6</strong>
                  <small>
                    Ground Truth ✓ · {document.reviewedFieldCount}/
                    {document.fieldCount} field · {document.sourceFormat}
                  </small>
                </button>
              ))}
            </div>
            <div className="heldout-preview">
              {activeCccdEvidenceDocument ? (
                <img
                  src={`${API_BASE}/cccd-heldout/review/document?id=${encodeURIComponent(
                    activeCccdEvidenceDocument.documentId,
                  )}&mode=preview`}
                  alt={`CCCD held-out ${activeCccdEvidenceDocument.documentId}`}
                />
              ) : (
                <div className="native-heldout-file">
                  <strong>Chưa có CCCD held-out mới</strong>
                </div>
              )}
              {activeCccdEvidenceDocument ? (
                <div className="heldout-preview-actions">
                  <div>
                    <strong>{activeCccdEvidenceDocument.documentId}</strong>
                    <span>
                      {activeCccdEvidenceDocument.sourceFile} · Ground Truth ✓ ·
                      Phase 11.6
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
            <aside className="evidence-inspector" aria-live="polite">
              <header>
                <div>
                  <span>SEALED PREDICTION / METRICS</span>
                  <strong>CCCD Phase 11.6</strong>
                </div>
                <small>
                  {groundTruthReview?.evaluation?.evaluatedAt ??
                    "Chưa có evaluate-once"}
                </small>
              </header>
              {cccdEvidenceMetrics ? (
                <div className="evidence-metrics-strip" data-testid="cccd-evidence-metrics">
                  <span>
                    Strict EM <strong>{pct(cccdEvidenceMetrics.strictFieldExactMatch ?? null, 2)}</strong>
                  </span>
                  <span>
                    ASCII EM <strong>{pct(cccdEvidenceMetrics.asciiFieldExactMatch ?? null, 2)}</strong>
                  </span>
                  <span>
                    CER <strong>{pct(cccdEvidenceMetrics.cer ?? null, 2)}</strong>
                  </span>
                  <span>
                    Field presence <strong>{pct(cccdEvidenceMetrics.fieldPresence ?? null, 2)}</strong>
                  </span>
                  <span>
                    Accepted precision <strong>{pct(cccdEvidenceMetrics.acceptedPrecision ?? null, 2)}</strong>
                  </span>
                </div>
              ) : null}
              <CccdEvaluationInspector
                detail={groundTruthEvaluationDetail}
                loading={isLoadingGroundTruthEvaluationDetail}
                error={groundTruthEvaluationDetailError}
              />
            </aside>
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
      </section>

      <section className="section next-section" id="next">
        <div className="section-heading">
          <div>
            <p className="eyebrow">RECOMMENDED NEXT</p>
            <h2>Giải quyết recognizer bằng bằng chứng thật</h2>
          </div>
          <p>
            Các luồng hiện tại vẫn cần kiểm tra theo từng loại tài liệu và field;
            chỉ chuyển dữ liệu sang workflow sau khi kết quả đã qua human review.
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
