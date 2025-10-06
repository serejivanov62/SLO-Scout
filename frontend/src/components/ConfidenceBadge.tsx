interface ConfidenceBadgeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

export default function ConfidenceBadge({ score, size = 'md' }: ConfidenceBadgeProps) {
  const getColor = (score: number) => {
    if (score >= 80) return 'bg-green-100 text-green-800';
    if (score >= 60) return 'bg-yellow-100 text-yellow-800';
    if (score >= 40) return 'bg-orange-100 text-orange-800';
    return 'bg-red-100 text-red-800';
  };

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-0.5',
    lg: 'text-base px-3 py-1',
  };

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full ${getColor(score)} ${sizeClasses[size]}`}
    >
      {score.toFixed(1)}% confidence
    </span>
  );
}
