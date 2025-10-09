import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { slisApi, slosApi } from '../services/api';
import SLIApprovalCard from '../components/SLIApprovalCard';
import { Target, TrendingUp, AlertCircle, Loader2, Plus, CheckCircle2 } from 'lucide-react';
import { SLI, SLO } from '../types';

export default function SLOsPage() {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedSli, setSelectedSli] = useState<SLI | null>(null);
  const [sloFormData, setSloFormData] = useState({
    threshold_value: '',
    comparison_operator: 'lte' as 'lt' | 'lte' | 'gt' | 'gte' | 'eq',
    time_window: '30d',
    target_percentage: '99.9',
    severity: 'high' as 'critical' | 'high' | 'medium' | 'low',
  });

  const queryClient = useQueryClient();

  const { data: slis = [], isLoading: slisLoading, error: slisError } = useQuery({
    queryKey: ['slis'],
    queryFn: slisApi.getAll,
  });

  const { data: slos = [], isLoading: slosLoading, error: slosError } = useQuery({
    queryKey: ['slos'],
    queryFn: slosApi.getAll,
  });

  const createSloMutation = useMutation({
    mutationFn: (data: {
      sli_id: string;
      threshold_value: number;
      comparison_operator: 'lt' | 'lte' | 'gt' | 'gte' | 'eq';
      time_window: string;
      target_percentage: number;
      severity: 'critical' | 'high' | 'medium' | 'low';
    }) => slosApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['slos'] });
      setShowCreateForm(false);
      setSelectedSli(null);
      setSloFormData({
        threshold_value: '',
        comparison_operator: 'lte',
        time_window: '30d',
        target_percentage: '99.9',
        severity: 'high',
      });
    },
  });

  const handleCreateSlo = () => {
    if (!selectedSli) return;

    createSloMutation.mutate({
      sli_id: selectedSli.id,
      threshold_value: parseFloat(sloFormData.threshold_value),
      comparison_operator: sloFormData.comparison_operator,
      time_window: sloFormData.time_window,
      target_percentage: parseFloat(sloFormData.target_percentage),
      severity: sloFormData.severity,
    });
  };

  const approvedSlis = slis.filter(sli => sli.approved_by);
  const pendingSlis = slis.filter(sli => !sli.approved_by);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'high':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'low':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getVariantColor = (variant: string) => {
    switch (variant) {
      case 'deployed':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'approved':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'proposal':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'retired':
        return 'bg-gray-100 text-gray-800 border-gray-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const calculateErrorBudgetStatus = (remaining: number) => {
    if (remaining >= 50) return { color: 'text-green-600', label: 'Healthy' };
    if (remaining >= 20) return { color: 'text-yellow-600', label: 'Warning' };
    return { color: 'text-red-600', label: 'Critical' };
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">SLOs & SLIs</h1>
        <p className="text-gray-600">
          Review and approve SLIs, create SLOs, and monitor error budgets
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-gray-200 mb-8">
        <nav className="-mb-px flex space-x-8" aria-label="Tabs">
          <a
            href="#slis"
            className="border-blue-500 text-blue-600 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm"
          >
            SLI Approval ({pendingSlis.length})
          </a>
          <a
            href="#slos"
            className="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm"
          >
            SLOs ({slos.length})
          </a>
        </nav>
      </div>

      {/* SLI Approval Section */}
      <section id="slis" className="mb-12">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-semibold text-gray-900">SLI Approval</h2>
          <button
            onClick={() => setShowCreateForm(true)}
            disabled={approvedSlis.length === 0}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            <Plus className="w-5 h-5" aria-hidden="true" />
            Create SLO
          </button>
        </div>

        {slisLoading ? (
          <div className="flex items-center justify-center py-12" role="status">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" aria-hidden="true" />
            <span className="sr-only">Loading SLIs...</span>
          </div>
        ) : slisError ? (
          <div className="bg-red-50 border border-red-200 rounded-md p-6" role="alert">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0" aria-hidden="true" />
              <div>
                <h3 className="text-lg font-medium text-red-800">Error loading SLIs</h3>
                <p className="text-sm text-red-700 mt-1">
                  {slisError instanceof Error ? slisError.message : 'Failed to load SLIs'}
                </p>
              </div>
            </div>
          </div>
        ) : pendingSlis.length === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <CheckCircle2 className="w-16 h-16 text-green-400 mx-auto mb-4" aria-hidden="true" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">All SLIs approved</h3>
            <p className="text-gray-600">
              There are no pending SLIs waiting for approval
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {pendingSlis.map((sli) => (
              <SLIApprovalCard
                key={sli.id}
                sli={sli}
                onApproved={() => queryClient.invalidateQueries({ queryKey: ['slis'] })}
              />
            ))}
          </div>
        )}
      </section>

      {/* Create SLO Form Modal */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Create SLO</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Select Approved SLI <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={selectedSli?.id || ''}
                    onChange={(e) => {
                      const sli = approvedSlis.find(s => s.id === e.target.value);
                      setSelectedSli(sli || null);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">-- Select an SLI --</option>
                    {approvedSlis.map((sli) => (
                      <option key={sli.id} value={sli.id}>
                        {sli.name} ({sli.metric_type})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Threshold Value <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={sloFormData.threshold_value}
                      onChange={(e) => setSloFormData({ ...sloFormData, threshold_value: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., 500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Comparison Operator <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={sloFormData.comparison_operator}
                      onChange={(e) => setSloFormData({ ...sloFormData, comparison_operator: e.target.value as any })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="lt">Less than (&lt;)</option>
                      <option value="lte">Less than or equal (&lt;=)</option>
                      <option value="gt">Greater than (&gt;)</option>
                      <option value="gte">Greater than or equal (&gt;=)</option>
                      <option value="eq">Equal (=)</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Time Window <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={sloFormData.time_window}
                      onChange={(e) => setSloFormData({ ...sloFormData, time_window: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="7d">7 days</option>
                      <option value="30d">30 days</option>
                      <option value="90d">90 days</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Target Percentage <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      max="100"
                      value={sloFormData.target_percentage}
                      onChange={(e) => setSloFormData({ ...sloFormData, target_percentage: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="e.g., 99.9"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Severity <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={sloFormData.severity}
                    onChange={(e) => setSloFormData({ ...sloFormData, severity: e.target.value as any })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>

                {createSloMutation.isError && (
                  <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700" role="alert">
                    {createSloMutation.error instanceof Error
                      ? createSloMutation.error.message
                      : 'Failed to create SLO'}
                  </div>
                )}
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={handleCreateSlo}
                  disabled={!selectedSli || !sloFormData.threshold_value || !sloFormData.target_percentage || createSloMutation.isPending}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {createSloMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                      Creating...
                    </>
                  ) : (
                    'Create SLO'
                  )}
                </button>
                <button
                  onClick={() => {
                    setShowCreateForm(false);
                    setSelectedSli(null);
                  }}
                  disabled={createSloMutation.isPending}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-500"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SLOs Section */}
      <section id="slos">
        <h2 className="text-2xl font-semibold text-gray-900 mb-6">SLOs & Error Budgets</h2>

        {slosLoading ? (
          <div className="flex items-center justify-center py-12" role="status">
            <Loader2 className="w-8 h-8 text-blue-600 animate-spin" aria-hidden="true" />
            <span className="sr-only">Loading SLOs...</span>
          </div>
        ) : slosError ? (
          <div className="bg-red-50 border border-red-200 rounded-md p-6" role="alert">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-red-600 flex-shrink-0" aria-hidden="true" />
              <div>
                <h3 className="text-lg font-medium text-red-800">Error loading SLOs</h3>
                <p className="text-sm text-red-700 mt-1">
                  {slosError instanceof Error ? slosError.message : 'Failed to load SLOs'}
                </p>
              </div>
            </div>
          </div>
        ) : slos.length === 0 ? (
          <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <Target className="w-16 h-16 text-gray-400 mx-auto mb-4" aria-hidden="true" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No SLOs yet</h3>
            <p className="text-gray-600 mb-4">
              Create your first SLO from an approved SLI
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {slos.map((slo) => {
              const budgetStatus = calculateErrorBudgetStatus(slo.error_budget_remaining);
              const relatedSli = slis.find(s => s.id === slo.sli_id);

              return (
                <div
                  key={slo.id}
                  className="bg-white border border-gray-200 rounded-lg shadow-sm p-6"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">
                        {relatedSli?.name || 'Unknown SLI'}
                      </h3>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2.5 py-0.5 text-xs font-medium rounded-md border ${getSeverityColor(slo.severity)}`}>
                          {slo.severity}
                        </span>
                        <span className={`px-2.5 py-0.5 text-xs font-medium rounded-md border ${getVariantColor(slo.variant)}`}>
                          {slo.variant}
                        </span>
                      </div>
                    </div>
                    <Target className="w-6 h-6 text-gray-400" aria-hidden="true" />
                  </div>

                  <div className="space-y-3 mb-4">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Target:</span>
                      <span className="font-medium text-gray-900">
                        {slo.comparison_operator} {slo.threshold_value} ({slo.target_percentage}%)
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-600">Time Window:</span>
                      <span className="font-medium text-gray-900">{slo.time_window}</span>
                    </div>
                  </div>

                  <div className="border-t border-gray-200 pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">Error Budget</span>
                      <span className={`text-2xl font-bold ${budgetStatus.color}`}>
                        {slo.error_budget_remaining.toFixed(1)}%
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          slo.error_budget_remaining >= 50
                            ? 'bg-green-500'
                            : slo.error_budget_remaining >= 20
                            ? 'bg-yellow-500'
                            : 'bg-red-500'
                        }`}
                        style={{ width: `${slo.error_budget_remaining}%` }}
                      />
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <TrendingUp className={`w-4 h-4 ${budgetStatus.color}`} aria-hidden="true" />
                      <span className={`text-sm font-medium ${budgetStatus.color}`}>
                        {budgetStatus.label}
                      </span>
                    </div>
                  </div>

                  <div className="text-xs text-gray-500 mt-4 pt-4 border-t border-gray-200">
                    <div>Created: {new Date(slo.created_at).toLocaleDateString()}</div>
                    <div className="font-mono mt-1">{slo.id}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
