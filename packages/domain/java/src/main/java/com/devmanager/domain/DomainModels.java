package com.devmanager.domain;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class DomainModels {
    private DomainModels() {
    }

    public enum TriggerType {
        SCHEDULED_DAILY("scheduled.daily"),
        MANUAL("manual"),
        GIT_PUSH("git.push"),
        PULL_REQUEST("pull_request"),
        CI_COMPLETED("ci.completed"),
        OBSERVABILITY_ALERT("observability.alert");

        private final String value;

        TriggerType(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum RunStatus {
        TRIGGER_RECEIVED("trigger_received"),
        AUTHORIZED("authorized"),
        BASELINE_RESOLVED("baseline_resolved"),
        REPOSITORY_FETCHED("repository_fetched"),
        DIFF_EXTRACTED("diff_extracted"),
        DATA_SANITIZED("data_sanitized"),
        CHANGE_CLASSIFIED("change_classified"),
        REVIEWS_DISPATCHED("reviews_dispatched"),
        FINDINGS_AGGREGATED("findings_aggregated"),
        FINDINGS_VALIDATED("findings_validated"),
        SCORE_CALCULATED("score_calculated"),
        POLICY_EVALUATED("policy_evaluated"),
        REPORT_GENERATED("report_generated"),
        BASELINE_COMMITTED("baseline_committed"),
        COMPLETED("completed"),
        PARTIAL_ANALYSIS("partial_analysis"),
        FAILED("failed"),
        REJECTED("rejected");

        private final String value;

        RunStatus(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum ChangeType {
        ADDED("added"),
        MODIFIED("modified"),
        DELETED("deleted"),
        RENAMED("renamed"),
        COPIED("copied"),
        TYPE_CHANGED("type_changed");

        private final String value;

        ChangeType(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum RiskTag {
        AUTHENTICATION("authentication"),
        AUTHORIZATION("authorization"),
        PUBLIC_API("public-api"),
        DATA_MIGRATION("data-migration"),
        SCHEMA_CHANGE("schema-change"),
        TRANSACTION("transaction"),
        CONCURRENCY("concurrency"),
        DEPENDENCY("dependency"),
        INFRASTRUCTURE("infrastructure"),
        DEPLOYMENT("deployment"),
        MISSING_TESTS("missing-tests"),
        HIGH_COMPLEXITY("high-complexity"),
        INCIDENT_RELATED("incident-related");

        private final String value;

        RiskTag(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum ReviewCategory {
        CORRECTNESS("correctness"),
        SECURITY("security"),
        TESTING("testing"),
        RELIABILITY("reliability"),
        ARCHITECTURE("architecture"),
        MAINTAINABILITY("maintainability"),
        PERFORMANCE("performance"),
        INFRASTRUCTURE("infrastructure"),
        KB_COMPLIANCE("kb_compliance");

        private final String value;

        ReviewCategory(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum Severity {
        CRITICAL("critical"),
        HIGH("high"),
        MEDIUM("medium"),
        LOW("low"),
        INFORMATIONAL("informational");

        private final String value;

        Severity(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum FindingStatus {
        OPEN("open"),
        ACCEPTED("accepted"),
        REJECTED("rejected"),
        DISPUTED("disputed"),
        RESOLVED("resolved");

        private final String value;

        FindingStatus(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum ScoreStatus {
        COMPLETE("complete"),
        INCOMPLETE("incomplete");

        private final String value;

        ScoreStatus(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum Grade {
        A_PLUS("A+"),
        A("A"),
        B("B"),
        C("C"),
        D("D"),
        F("F");

        private final String value;

        Grade(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum AuditEventType {
        WORKFLOW_TRANSITION("workflow.transition"),
        TOOL_INVOCATION("tool.invocation"),
        MODEL_INVOCATION("model.invocation"),
        POLICY_DECISION("policy.decision"),
        APPROVAL_DECISION("approval.decision"),
        REPORT_GENERATED("report.generated");

        private final String value;

        AuditEventType(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum PolicyDecisionValue {
        ALLOWED("allowed"),
        DENIED("denied"),
        APPROVAL_REQUIRED("approval_required");

        private final String value;

        PolicyDecisionValue(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public enum PublicationChannel {
        INTERNAL_MARKDOWN("internal_markdown"),
        PULL_REQUEST_COMMENT("pull_request_comment"),
        ISSUE("issue"),
        SLACK("slack"),
        FEISHU("feishu"),
        DASHBOARD("dashboard");

        private final String value;

        PublicationChannel(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public record Repository(
            UUID repositoryId,
            String provider,
            String fullName,
            String defaultBranch,
            String ownerTeam,
            String policyId,
            String status,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt
    ) {
    }

    public record TriggerEvent(
            UUID eventId,
            TriggerType eventType,
            String source,
            OffsetDateTime timestamp,
            String repository,
            String targetBranch,
            String targetSha,
            String actor,
            UUID correlationId,
            String payloadReference
    ) {
    }

    public record AnalysisRun(
            UUID runId,
            UUID repositoryId,
            UUID triggerId,
            TriggerType triggerType,
            String targetBranch,
            String baselineSha,
            String targetSha,
            String mergeBaseSha,
            boolean historyRewriteDetected,
            RunStatus status,
            String policyVersion,
            String scoringVersion,
            Map<String, String> agentVersions,
            String failureReason,
            OffsetDateTime startedAt,
            OffsetDateTime completedAt
    ) {
    }

    public record Baseline(
            UUID repositoryId,
            String branch,
            String lastSuccessfulSha,
            UUID runId,
            OffsetDateTime updatedAt
    ) {
    }

    public record ChangeUnit(
            UUID changeUnitId,
            UUID runId,
            String repository,
            String baselineSha,
            String targetSha,
            String filePath,
            String previousFilePath,
            ChangeType changeType,
            String language,
            String owner,
            int addedLines,
            int deletedLines,
            boolean binary,
            boolean generated,
            boolean vendor,
            boolean testFile,
            List<RiskTag> riskTags,
            String hunksRef
    ) {
    }

    public record ReviewTaskConstraints(
            int maxFindings,
            boolean requireLineEvidence,
            boolean externalActionsAllowed
    ) {
    }

    public record ReviewTask(
            UUID taskId,
            UUID runId,
            ReviewCategory category,
            List<UUID> changeUnitIds,
            List<String> toolEvidenceRefs,
            List<String> knowledgeContextRefs,
            ReviewTaskConstraints constraints
    ) {
    }

    public record ReviewerFinding(
            String findingId,
            UUID runId,
            ReviewCategory category,
            Severity severity,
            double confidence,
            String repository,
            String commitSha,
            String file,
            int startLine,
            int endLine,
            String observation,
            String impact,
            String recommendation,
            String verification,
            List<String> evidenceRefs,
            List<String> relatedKnowledgeRefs,
            FindingStatus status,
            String dedupeKey
    ) {
    }

    public record ScoreDeduction(
            String findingId,
            String category,
            String severity,
            double rawDeduction,
            double adjustedDeduction,
            String capApplied
    ) {
    }

    public record Score(
            UUID scoreId,
            UUID runId,
            String scoringVersion,
            ScoreStatus status,
            Double finalScore,
            Grade grade,
            Double confidence,
            List<ScoreDeduction> deductions,
            List<String> caps,
            List<String> limitations,
            OffsetDateTime createdAt
    ) {
    }

    public record PolicyDecision(
            UUID decisionId,
            UUID runId,
            String action,
            PolicyDecisionValue decision,
            String reason,
            String policyVersion,
            String approvedBy,
            OffsetDateTime createdAt
    ) {
    }

    public record AuditEvent(
            UUID eventId,
            String actor,
            UUID workflowId,
            AuditEventType eventType,
            String tool,
            String inputRef,
            String outputRef,
            String modelVersion,
            String promptVersion,
            String policyVersion,
            PolicyDecisionValue policyDecision,
            String approvalIdentity,
            Map<String, Object> metadata,
            OffsetDateTime timestamp
    ) {
    }

    public record ReportPublicationRequest(
            UUID requestId,
            UUID reportId,
            PublicationChannel channel,
            String destination,
            boolean approvalRequired,
            String contentReference,
            String policyVersion
    ) {
    }
}
