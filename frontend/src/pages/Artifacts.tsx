import { useQuery } from '@tanstack/react-query';
import { FileText, CheckCircle, XCircle, Clock, Rocket } from 'lucide-react';

export default function Artifacts() {
  // Mock query - would normally fetch all artifacts
  const { data: artifacts, isLoading } = useQuery({
    queryKey: ['artifacts'],
    queryFn: async () => {
      // For now, return empty array - backend doesn't have this endpoint yet
      return [];
    },
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'passed':
        return <CheckCircle className="h-5 w-5 text-green-600" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-600" />;
      default:
        return <Clock className="h-5 w-5 text-yellow-600" />;
    }
  };

  const getDeploymentBadge = (status: string) => {
    const badges: Record<string, string> = {
      deployed: 'bg-green-100 text-green-800',
      deploying: 'bg-blue-100 text-blue-800',
      not_deployed: 'bg-gray-100 text-gray-800',
      failed: 'bg-red-100 text-red-800',
    };
    return badges[status] || badges.not_deployed;
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div>
      <div className="sm:flex sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Artifacts</h1>
          <p className="mt-2 text-sm text-gray-700">
            Generated Prometheus rules, Grafana dashboards, and runbooks
          </p>
        </div>
      </div>

      {!artifacts || artifacts.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <FileText className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No artifacts generated yet</h3>
          <p className="mt-1 text-sm text-gray-500">
            Artifacts will appear here after SLO approval
          </p>
        </div>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  SLO
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Validation
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Approval
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Deployment
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Version
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {artifacts.map((artifact: any) => (
                <tr key={artifact.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {artifact.artifact_type.replace('_', ' ')}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {artifact.slo_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      {getStatusIcon(artifact.validation_status)}
                      <span className="ml-2 text-sm text-gray-900 capitalize">
                        {artifact.validation_status}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      {getStatusIcon(artifact.approval_status)}
                      <span className="ml-2 text-sm text-gray-900 capitalize">
                        {artifact.approval_status}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getDeploymentBadge(
                        artifact.deployment_status
                      )}`}
                    >
                      {artifact.deployment_status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    v{artifact.version}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {artifact.deployment_status === 'not_deployed' &&
                      artifact.approval_status === 'approved' && (
                        <button className="text-blue-600 hover:text-blue-900 inline-flex items-center">
                          <Rocket className="h-4 w-4 mr-1" />
                          Deploy
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
