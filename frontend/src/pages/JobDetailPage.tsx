import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { jobsApi } from '../api/jobs';
import { cn, formatFileSize, formatDate } from '../lib/utils';
import Layout from '../components/layout/Layout';
import Button from '../components/ui/Button';
import Card, { CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import Progress from '../components/ui/Progress';
import {
  ArrowLeft,
  Download,
  Pause,
  Play,
  Trash2,
  FileText,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  AlertCircle,
  Coins,
} from 'lucide-react';

const statusConfig = {
  pending: { icon: Clock, color: 'text-foreground-muted', bg: 'bg-foreground-muted/10', label: 'Pending' },
  processing: { icon: Loader2, color: 'text-accent', bg: 'bg-accent/10', label: 'Processing', animate: true },
  paused: { icon: Pause, color: 'text-warning', bg: 'bg-warning/10', label: 'Paused' },
  completed: { icon: CheckCircle, color: 'text-success', bg: 'bg-success/10', label: 'Completed' },
  failed: { icon: XCircle, color: 'text-danger', bg: 'bg-danger/10', label: 'Failed' },
  cancelled: { icon: XCircle, color: 'text-foreground-subtle', bg: 'bg-background-tertiary', label: 'Cancelled' },
};

function StatCard({ label, value, icon: Icon }: { label: string; value: string; icon: React.ElementType }) {
  return (
    <div className="flex items-center gap-4 p-4 bg-background-tertiary rounded-lg">
      <div className="p-2 bg-background rounded-lg">
        <Icon className="w-5 h-5 text-foreground-muted" />
      </div>
      <div>
        <p className="text-sm text-foreground-muted">{label}</p>
        <p className="text-lg font-semibold text-foreground">{value}</p>
      </div>
    </div>
  );
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: job, isLoading, error } = useQuery({
    queryKey: ['job', id],
    queryFn: () => jobsApi.get(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      // Faster refresh while processing
      const data = query.state.data;
      if (data?.status === 'processing' || data?.status === 'pending') {
        return 3000;
      }
      return false;
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => jobsApi.pause(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['job', id] }),
  });

  const resumeMutation = useMutation({
    mutationFn: () => jobsApi.resume(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['job', id] }),
  });

  const cancelMutation = useMutation({
    mutationFn: () => jobsApi.cancel(id!),
    onSuccess: () => navigate('/'),
  });

  if (isLoading) {
    return (
      <Layout>
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 text-accent animate-spin" />
        </div>
      </Layout>
    );
  }

  if (error || !job) {
    return (
      <Layout>
        <div className="text-center py-24">
          <AlertCircle className="w-12 h-12 text-danger mx-auto mb-4" />
          <p className="text-foreground">Job not found</p>
          <Button variant="secondary" className="mt-4" onClick={() => navigate('/')}>
            Back to Dashboard
          </Button>
        </div>
      </Layout>
    );
  }

  const config = statusConfig[job.status];
  const Icon = config.icon;

  return (
    <Layout>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <div className="w-px h-8 bg-border" />
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background-tertiary rounded-lg">
              <FileText className="w-6 h-6 text-foreground-muted" />
            </div>
            <div>
              <h1 className="text-xl font-display font-bold text-foreground">
                {job.source_file_name}
              </h1>
              <p className="text-sm text-foreground-subtle">
                {formatFileSize(job.source_file_size_bytes)} • Uploaded {formatDate(job.created_at)}
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {job.status === 'processing' && (
            <Button
              variant="secondary"
              onClick={() => pauseMutation.mutate()}
              isLoading={pauseMutation.isPending}
            >
              <Pause className="w-4 h-4 mr-2" />
              Pause
            </Button>
          )}
          {job.status === 'paused' && (
            <Button
              variant="primary"
              onClick={() => resumeMutation.mutate()}
              isLoading={resumeMutation.isPending}
            >
              <Play className="w-4 h-4 mr-2" />
              Resume
            </Button>
          )}
          {job.status === 'completed' && (
            <Button
              variant="primary"
              onClick={() => window.open(jobsApi.getDownloadUrl(job.id), '_blank')}
            >
              <Download className="w-4 h-4 mr-2" />
              Download
            </Button>
          )}
          {!['completed', 'cancelled'].includes(job.status) && (
            <Button
              variant="danger"
              onClick={() => cancelMutation.mutate()}
              isLoading={cancelMutation.isPending}
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Status Badge */}
      <div className="mb-8">
        <div className={cn('inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium', config.bg, config.color)}>
          <Icon className={cn('w-4 h-4', 'animate' in config && config.animate && 'animate-spin')} />
          {config.label}
          {job.current_phase && (
            <>
              <span className="text-foreground-subtle">•</span>
              <span className="capitalize">{job.current_phase}</span>
            </>
          )}
        </div>
      </div>

      {/* Progress Section */}
      {(job.status === 'processing' || job.status === 'paused' || job.total_units > 0) && (
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Translation Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-4">
              <span className="text-foreground-muted">
                {job.completed_units} of {job.total_units} units completed
              </span>
              <span className="text-2xl font-bold text-foreground">
                {job.progress_percent.toFixed(1)}%
              </span>
            </div>
            <Progress value={job.progress_percent} size="lg" />
          </CardContent>
        </Card>
      )}

      {/* Error Display */}
      {job.last_error && (
        <Card className="mb-8 border-danger/30 bg-danger/5">
          <CardContent className="flex items-start gap-3 py-4">
            <AlertCircle className="w-5 h-5 text-danger shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-danger mb-1">Error</p>
              <p className="text-sm text-foreground-muted">{job.last_error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Source Language"
          value={job.source_language === 'ko' ? 'Korean' : job.source_language}
          icon={FileText}
        />
        <StatCard
          label="Target Language"
          value={job.target_language === 'en' ? 'English' : job.target_language}
          icon={FileText}
        />
        <StatCard
          label="Input Tokens"
          value={job.total_input_tokens.toLocaleString()}
          icon={Coins}
        />
        <StatCard
          label="Output Tokens"
          value={job.total_output_tokens.toLocaleString()}
          icon={Coins}
        />
      </div>

      {/* Timeline */}
      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="w-2 h-2 bg-success rounded-full" />
              <div>
                <p className="text-sm font-medium text-foreground">Created</p>
                <p className="text-sm text-foreground-subtle">{formatDate(job.created_at)}</p>
              </div>
            </div>
            {job.started_at && (
              <div className="flex items-center gap-4">
                <div className="w-2 h-2 bg-accent rounded-full" />
                <div>
                  <p className="text-sm font-medium text-foreground">Started Processing</p>
                  <p className="text-sm text-foreground-subtle">{formatDate(job.started_at)}</p>
                </div>
              </div>
            )}
            {job.completed_at && (
              <div className="flex items-center gap-4">
                <div className={cn('w-2 h-2 rounded-full', job.status === 'completed' ? 'bg-success' : 'bg-danger')} />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {job.status === 'completed' ? 'Completed' : 'Ended'}
                  </p>
                  <p className="text-sm text-foreground-subtle">{formatDate(job.completed_at)}</p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </Layout>
  );
}

