import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { slisApi } from '../services/api';
import { SLI } from '../types';
import { CheckCircle2, Clock, User, Activity, AlertCircle, Loader2 } from 'lucide-react';
import ConfidenceBadge from './ConfidenceBadge';

interface SLIApprovalCardProps {
  sli: SLI;
  onApproved?: (sli: SLI) => void;
}

export default function SLIApprovalCard({ sli, onApproved }: SLIApprovalCardProps) {
  const [approverName, setApproverName] = useState('');
  const [showApprovalForm, setShowApprovalForm] = useState(false);
  const queryClient = useQueryClient();

  const approveMutation = useMutation({
    mutationFn: (approvedBy: string) => slisApi.approve(sli.id, approvedBy),
    onSuccess: (updatedSli) => {
      queryClient.invalidateQueries({ queryKey: ['slis'] });
      queryClient.invalidateQueries({ queryKey: ['sli', sli.id] });
      setShowApprovalForm(false);
      setApproverName('');
      if (onApproved) {
        onApproved(updatedSli);
      }
    },
  });

  const isApproved = !!sli.approved_by;

  const getMetricTypeColor = (type: SLI['metric_type']) => {
    switch (type) {
      case 'latency':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'availability':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'error_rate':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'throughput':
        return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'saturation':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getMetricTypeIcon = (type: SLI['metric_type']) => {
    switch (type) {
      case 'latency':
        return <Clock className="w-4 h-4" aria-hidden="true" />;
      case 'availability':
        return <CheckCircle2 className="w-4 h-4" aria-hidden="true" />;
      case 'error_rate':
        return <AlertCircle className="w-4 h-4" aria-hidden="true" />;
      case 'throughput':
      case 'saturation':
        return <Activity className="w-4 h-4" aria-hidden="true" />;
      default:
        return <Activity className="w-4 h-4" aria-hidden="true" />;
    }
  };

  const handleApprove = () => {
    if (!approverName.trim()) return;
    approveMutation.mutate(approverName.trim());
  };

  const formatValue = (value: number | null) => {
    if (value === null) return 'N/A';
    return `${value.toFixed(2)} ${sli.unit}`;
  };

  return (
    <div
      className={`bg-white border-2 rounded-lg shadow-sm transition-all ${
        isApproved ? 'border-green-300' : 'border-gray-200 hover:border-blue-300'
      }`}
    >
      <div className="p-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-lg font-semibold text-gray-900">{sli.name}</h3>
              {isApproved && (
                <CheckCircle2 className="w-5 h-5 text-green-600" aria-label="Approved" />
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-xs font-medium rounded-md border ${getMetricTypeColor(sli.metric_type)}`}
              >
                {getMetricTypeIcon(sli.metric_type)}
                {sli.metric_type.replace('_', ' ')}
              </span>
              <ConfidenceBadge score={sli.confidence_score} />
            </div>
          </div>
        </div>

        {/* Metric Definition */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Metric Definition (PromQL)
          </label>
          <div className="bg-gray-50 border border-gray-200 rounded-md p-3">
            <code className="text-sm font-mono text-gray-900 break-all">
              {sli.metric_definition}
            </code>
          </div>
        </div>

        {/* Current Value */}
        {sli.current_value !== null && (
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Current Value
            </label>
            <div className="text-2xl font-semibold text-gray-900">
              {formatValue(sli.current_value)}
            </div>
          </div>
        )}

        {/* Evidence Pointers */}
        {sli.evidence_pointers && sli.evidence_pointers.length > 0 && (
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Evidence ({sli.evidence_pointers.length})
            </label>
            <div className="space-y-2">
              {sli.evidence_pointers.slice(0, 3).map((evidence, index) => (
                <div
                  key={index}
                  className="bg-blue-50 border border-blue-200 rounded-md px-3 py-2 text-sm"
                >
                  <div className="font-medium text-blue-900">{evidence.type}</div>
                  <div className="text-blue-700 font-mono text-xs mt-1 truncate">
                    {evidence.reference}
                  </div>
                </div>
              ))}
              {sli.evidence_pointers.length > 3 && (
                <div className="text-sm text-gray-600 text-center">
                  +{sli.evidence_pointers.length - 3} more
                </div>
              )}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div className="text-sm text-gray-600 mb-4 border-t border-gray-200 pt-4">
          <div className="flex items-center justify-between">
            <span>Created: {new Date(sli.created_at).toLocaleDateString()}</span>
            <span className="font-mono text-xs">{sli.id}</span>
          </div>
        </div>

        {/* Approval Section */}
        {isApproved ? (
          <div className="bg-green-50 border border-green-200 rounded-md p-4">
            <div className="flex items-center gap-2 text-green-800">
              <User className="w-5 h-5" aria-hidden="true" />
              <div>
                <div className="font-medium">Approved by</div>
                <div className="text-sm">{sli.approved_by}</div>
              </div>
            </div>
          </div>
        ) : (
          <div>
            {!showApprovalForm ? (
              <button
                onClick={() => setShowApprovalForm(true)}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
              >
                Approve SLI
              </button>
            ) : (
              <div className="space-y-3">
                <div>
                  <label htmlFor={`approver-${sli.id}`} className="block text-sm font-medium text-gray-700 mb-1">
                    Approver Name <span className="text-red-500" aria-label="required">*</span>
                  </label>
                  <input
                    type="text"
                    id={`approver-${sli.id}`}
                    value={approverName}
                    onChange={(e) => setApproverName(e.target.value)}
                    placeholder="Enter your name"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={approveMutation.isPending}
                    aria-invalid={approveMutation.isError}
                  />
                </div>

                {approveMutation.isError && (
                  <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700" role="alert">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
                      <span>
                        {approveMutation.error instanceof Error
                          ? approveMutation.error.message
                          : 'Failed to approve SLI. Please try again.'}
                      </span>
                    </div>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={handleApprove}
                    disabled={!approverName.trim() || approveMutation.isPending}
                    className="flex-1 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                  >
                    {approveMutation.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                        Approving...
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                        Confirm Approval
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => {
                      setShowApprovalForm(false);
                      setApproverName('');
                    }}
                    disabled={approveMutation.isPending}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
