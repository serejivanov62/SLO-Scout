import { useState, useEffect } from 'react';
import { Artifact } from '../types';
import { FileCode, CheckCircle2, XCircle, Clock, Copy, Check, Download } from 'lucide-react';

interface ArtifactViewerProps {
  artifact: Artifact;
  showActions?: boolean;
  onValidate?: (artifactId: string) => void;
  onApprove?: (artifactId: string) => void;
  onDeploy?: (artifactId: string) => void;
}

export default function ArtifactViewer({
  artifact,
  showActions = true,
  onValidate,
  onApprove,
  onDeploy,
}: ArtifactViewerProps) {
  const [copied, setCopied] = useState(false);
  const [highlightedContent, setHighlightedContent] = useState<string>('');

  useEffect(() => {
    // Basic syntax highlighting for YAML and JSON
    const content = artifact.content;
    let highlighted = content;

    if (artifact.artifact_type.includes('prometheus') || artifact.artifact_type.includes('yaml')) {
      // Simple YAML highlighting
      highlighted = content
        .split('\n')
        .map(line => {
          if (line.trim().startsWith('#')) {
            return `<span class="text-gray-500">${escapeHtml(line)}</span>`;
          } else if (line.includes(':')) {
            const [key, ...valueParts] = line.split(':');
            const value = valueParts.join(':');
            return `<span class="text-blue-600">${escapeHtml(key)}</span>:<span class="text-gray-900">${escapeHtml(value)}</span>`;
          }
          return escapeHtml(line);
        })
        .join('\n');
    } else if (artifact.artifact_type.includes('json') || content.trim().startsWith('{')) {
      // Simple JSON highlighting
      try {
        const parsed = JSON.parse(content);
        highlighted = JSON.stringify(parsed, null, 2)
          .split('\n')
          .map(line => {
            if (line.includes(':')) {
              const match = line.match(/^(\s*)"([^"]+)":\s*(.+)$/);
              if (match) {
                const [, indent, key, value] = match;
                return `${indent}<span class="text-purple-600">"${escapeHtml(key)}"</span>: <span class="text-gray-900">${escapeHtml(value)}</span>`;
              }
            }
            return escapeHtml(line);
          })
          .join('\n');
      } catch {
        highlighted = escapeHtml(content);
      }
    } else {
      highlighted = escapeHtml(content);
    }

    setHighlightedContent(highlighted);
  }, [artifact.content, artifact.artifact_type]);

  const escapeHtml = (text: string) => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const handleDownload = () => {
    const extension = artifact.artifact_type.includes('json') ? 'json' : 'yaml';
    const blob = new Blob([artifact.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.artifact_type}_v${artifact.version}.${extension}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getArtifactTypeLabel = (type: Artifact['artifact_type']) => {
    return type.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  const getArtifactTypeColor = (type: Artifact['artifact_type']) => {
    switch (type) {
      case 'prometheus_rule':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'grafana_dashboard':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'runbook':
        return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'alert_definition':
        return 'bg-red-100 text-red-800 border-red-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getStatusIcon = (status: string) => {
    if (status === 'passed' || status === 'approved' || status === 'deployed') {
      return <CheckCircle2 className="w-4 h-4 text-green-600" aria-hidden="true" />;
    } else if (status === 'failed' || status === 'rejected') {
      return <XCircle className="w-4 h-4 text-red-600" aria-hidden="true" />;
    } else {
      return <Clock className="w-4 h-4 text-yellow-600" aria-hidden="true" />;
    }
  };

  const getStatusColor = (status: string) => {
    if (status === 'passed' || status === 'approved' || status === 'deployed') {
      return 'bg-green-100 text-green-800 border-green-200';
    } else if (status === 'failed' || status === 'rejected') {
      return 'bg-red-100 text-red-800 border-red-200';
    } else if (status === 'deploying') {
      return 'bg-blue-100 text-blue-800 border-blue-200';
    } else {
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    }
  };

  const canValidate = artifact.validation_status === 'pending' && onValidate;
  const canApprove = artifact.validation_status === 'passed' &&
                     artifact.approval_status === 'pending' &&
                     onApprove;
  const canDeploy = artifact.approval_status === 'approved' &&
                    artifact.deployment_status === 'not_deployed' &&
                    onDeploy;

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <FileCode className="w-5 h-5 text-gray-600" aria-hidden="true" />
              <h3 className="text-lg font-semibold text-gray-900">
                {getArtifactTypeLabel(artifact.artifact_type)}
              </h3>
              <span
                className={`px-2.5 py-0.5 text-xs font-medium rounded-md border ${getArtifactTypeColor(artifact.artifact_type)}`}
              >
                v{artifact.version}
              </span>
            </div>

            <div className="flex items-center gap-3 flex-wrap text-sm">
              <div className="flex items-center gap-1">
                <span className="text-gray-600">Validation:</span>
                {getStatusIcon(artifact.validation_status)}
                <span
                  className={`px-2 py-0.5 text-xs font-medium rounded border ${getStatusColor(artifact.validation_status)}`}
                >
                  {artifact.validation_status}
                </span>
              </div>

              <div className="flex items-center gap-1">
                <span className="text-gray-600">Approval:</span>
                {getStatusIcon(artifact.approval_status)}
                <span
                  className={`px-2 py-0.5 text-xs font-medium rounded border ${getStatusColor(artifact.approval_status)}`}
                >
                  {artifact.approval_status}
                </span>
              </div>

              <div className="flex items-center gap-1">
                <span className="text-gray-600">Deployment:</span>
                {getStatusIcon(artifact.deployment_status)}
                <span
                  className={`px-2 py-0.5 text-xs font-medium rounded border ${getStatusColor(artifact.deployment_status)}`}
                >
                  {artifact.deployment_status.replace('_', ' ')}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={handleCopy}
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-200 rounded-md transition-colors"
              aria-label="Copy to clipboard"
              title="Copy to clipboard"
            >
              {copied ? (
                <Check className="w-4 h-4 text-green-600" aria-hidden="true" />
              ) : (
                <Copy className="w-4 h-4" aria-hidden="true" />
              )}
            </button>
            <button
              onClick={handleDownload}
              className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-200 rounded-md transition-colors"
              aria-label="Download artifact"
              title="Download artifact"
            >
              <Download className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 bg-gray-900 overflow-x-auto">
        <pre className="text-sm">
          <code
            className="text-gray-100 font-mono"
            dangerouslySetInnerHTML={{ __html: highlightedContent }}
          />
        </pre>
      </div>

      {/* Actions */}
      {showActions && (canValidate || canApprove || canDeploy) && (
        <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center gap-3">
            {canValidate && (
              <button
                onClick={() => onValidate(artifact.id)}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors text-sm font-medium"
              >
                Validate Artifact
              </button>
            )}

            {canApprove && (
              <button
                onClick={() => onApprove(artifact.id)}
                className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-colors text-sm font-medium"
              >
                Approve Artifact
              </button>
            )}

            {canDeploy && (
              <button
                onClick={() => onDeploy(artifact.id)}
                className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 transition-colors text-sm font-medium"
              >
                Deploy Artifact
              </button>
            )}
          </div>
        </div>
      )}

      {/* Metadata */}
      <div className="px-6 py-3 border-t border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between text-xs text-gray-600">
          <span>Created: {new Date(artifact.created_at).toLocaleString()}</span>
          <span className="font-mono">{artifact.id}</span>
        </div>
      </div>
    </div>
  );
}
