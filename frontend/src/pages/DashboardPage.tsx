import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import { useNavigate } from 'react-router-dom';
import { jobsApi } from '../api/jobs';
import type { Job } from '../api/jobs';
import { cn, formatFileSize, formatDate } from '../lib/utils';
import Layout from '../components/layout/Layout';
import Card from '../components/ui/Card';
import Progress from '../components/ui/Progress';
import {
  Upload,
  FileText,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  Pause,
} from 'lucide-react';

const statusConfig = {
  pending: { icon: Clock, color: 'text-foreground-muted', bg: 'bg-foreground-muted/10', label: 'Pending' },
  processing: { icon: Loader2, color: 'text-accent', bg: 'bg-accent/10', label: 'Processing', animate: true },
  paused: { icon: Pause, color: 'text-warning', bg: 'bg-warning/10', label: 'Paused' },
  completed: { icon: CheckCircle, color: 'text-success', bg: 'bg-success/10', label: 'Completed' },
  failed: { icon: XCircle, color: 'text-danger', bg: 'bg-danger/10', label: 'Failed' },
  cancelled: { icon: XCircle, color: 'text-foreground-subtle', bg: 'bg-background-tertiary', label: 'Cancelled' },
};

function JobCard({ job }: { job: Job }) {
  const navigate = useNavigate();
  const config = statusConfig[job.status];
  const Icon = config.icon;

  return (
    <Card
      variant="hover"
      className="cursor-pointer"
      onClick={() => navigate(`/jobs/${job.id}`)}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-background-tertiary rounded-lg">
            <FileText className="w-6 h-6 text-foreground-muted" />
          </div>
          <div>
            <h3 className="font-medium text-foreground mb-1">{job.source_file_name}</h3>
            <p className="text-sm text-foreground-subtle">
              {formatFileSize(job.source_file_size_bytes)} • {formatDate(job.created_at)}
            </p>
          </div>
        </div>
        <div className={cn('flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium', config.bg, config.color)}>
          <Icon className={cn('w-4 h-4', 'animate' in config && config.animate && 'animate-spin')} />
          {config.label}
        </div>
      </div>

      {(job.status === 'processing' || job.status === 'paused') && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-foreground-muted">
              {job.completed_units} / {job.total_units} units
            </span>
            <span className="text-sm font-medium text-foreground">
              {job.progress_percent.toFixed(1)}%
            </span>
          </div>
          <Progress value={job.progress_percent} />
        </div>
      )}

      {job.last_error && (
        <div className="mt-4 flex items-center gap-2 p-3 bg-danger/10 rounded-lg text-danger text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span className="truncate">{job.last_error}</span>
        </div>
      )}
    </Card>
  );
}

function UploadZone({ onUpload }: { onUpload: (file: File) => void }) {
  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      onUpload(acceptedFiles[0]);
    }
  }, [onUpload]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    },
    maxFiles: 1,
    maxSize: 50 * 1024 * 1024, // 50MB
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200',
        isDragActive
          ? 'border-accent bg-accent/5'
          : 'border-border hover:border-foreground-subtle hover:bg-background-secondary'
      )}
    >
      <input {...getInputProps()} />
      <div className="p-4 bg-accent/10 rounded-full w-fit mx-auto mb-4">
        <Upload className="w-8 h-8 text-accent" />
      </div>
      <p className="text-foreground font-medium mb-2">
        {isDragActive ? 'Drop file here' : 'Drop a document or click to upload'}
      </p>
      <p className="text-sm text-foreground-subtle">
        PDF or DOCX, up to 50MB
      </p>
    </div>
  );
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [isUploading, setIsUploading] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => jobsApi.list(),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const createMutation = useMutation({
    mutationFn: (file: File) => jobsApi.create({ file }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      setIsUploading(false);
    },
    onError: () => {
      setIsUploading(false);
    },
  });

  const handleUpload = (file: File) => {
    setIsUploading(true);
    createMutation.mutate(file);
  };

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-2xl font-display font-bold text-foreground mb-2">
          Translation Jobs
        </h1>
        <p className="text-foreground-muted">
          Upload documents to translate from Korean to English
        </p>
      </div>

      {/* Upload Zone */}
      <div className="mb-8">
        {isUploading ? (
          <Card className="p-8 text-center">
            <Loader2 className="w-8 h-8 text-accent animate-spin mx-auto mb-4" />
            <p className="text-foreground">Uploading document...</p>
          </Card>
        ) : (
          <UploadZone onUpload={handleUpload} />
        )}
      </div>

      {/* Jobs List */}
      <div>
        <h2 className="text-lg font-semibold text-foreground mb-4">Recent Jobs</h2>
        
        {isLoading ? (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-accent animate-spin mx-auto mb-4" />
            <p className="text-foreground-muted">Loading jobs...</p>
          </div>
        ) : data?.jobs.length === 0 ? (
          <Card className="text-center py-12">
            <FileText className="w-12 h-12 text-foreground-subtle mx-auto mb-4" />
            <p className="text-foreground mb-2">No jobs yet</p>
            <p className="text-sm text-foreground-subtle">
              Upload a document to get started
            </p>
          </Card>
        ) : (
          <div className="grid gap-4">
            {data?.jobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}

