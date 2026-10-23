// components/StatusBadge.tsx — Colour-coded shipment/approval status pill

interface Props {
  status: string;
  size?: "sm" | "md";
}

const STATUS_STYLES: Record<string, string> = {
  // Shipment states
  OBSERVE:            "bg-gray-100 text-gray-600",
  REASON:             "bg-gray-100 text-gray-600",
  PLAN:               "bg-gray-100 text-gray-600",
  POLICY_CHECK:       "bg-gray-100 text-gray-600",
  ACT:                "bg-blue-100 text-blue-700",
  VERIFY:             "bg-blue-100 text-blue-700",
  WAIT_EVENT:         "bg-yellow-100 text-yellow-700",
  COLLECT_DATA:       "bg-orange-100 text-orange-700",
  ESCALATE:           "bg-orange-100 text-orange-700",
  CUSTOMS_HOLD:       "bg-red-100 text-red-700",
  RECOVER:            "bg-red-100 text-red-700",
  CLEARANCE_VERIFIED: "bg-green-100 text-green-700",
  // Approval states
  PENDING:            "bg-blue-100 text-blue-700",
  APPROVED:           "bg-green-100 text-green-700",
  REJECTED:           "bg-red-100 text-red-700",
  EXPIRED:            "bg-gray-100 text-gray-500",
};

export default function StatusBadge({ status, size = "md" }: Props) {
  const style = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
  const padding = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs";
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${padding} ${style}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
