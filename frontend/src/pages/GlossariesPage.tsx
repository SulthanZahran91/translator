import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Layout from '../components/layout/Layout';
import Button from '../components/ui/Button';
import Card, { CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import Input from '../components/ui/Input';
import {
  Plus,
  Book,
  Loader2,
  Trash2,
  Search,
  X,
} from 'lucide-react';
import { cn } from '../lib/utils';
import apiClient from '../api/client';

interface Glossary {
  id: string;
  name: string;
  description: string | null;
  domain: string | null;
  term_count: number;
  created_at: string;
  updated_at: string;
}

interface GlossaryListResponse {
  glossaries: Glossary[];
  total: number;
}

interface Term {
  id: string;
  source_term: string;
  target_term: string;
  context: string | null;
  domain: string | null;
  definition: string | null;
  confidence: string;
  occurrence_count: number;
  created_at: string;
}

interface TermListResponse {
  terms: Term[];
  total: number;
}

const glossaryApi = {
  async list(): Promise<GlossaryListResponse> {
    const response = await apiClient.get<GlossaryListResponse>('/glossaries');
    return response.data;
  },
  async create(data: { name: string; description?: string; domain?: string }): Promise<Glossary> {
    const response = await apiClient.post<Glossary>('/glossaries', data);
    return response.data;
  },
  async delete(id: string): Promise<void> {
    await apiClient.delete(`/glossaries/${id}`);
  },
  async listTerms(glossaryId: string, search?: string): Promise<TermListResponse> {
    const response = await apiClient.get<TermListResponse>(`/glossaries/${glossaryId}/terms`, {
      params: { search },
    });
    return response.data;
  },
  async addTerm(glossaryId: string, data: { source_term: string; target_term: string }): Promise<Term> {
    const response = await apiClient.post<Term>(`/glossaries/${glossaryId}/terms`, data);
    return response.data;
  },
  async deleteTerm(glossaryId: string, termId: string): Promise<void> {
    await apiClient.delete(`/glossaries/${glossaryId}/terms/${termId}`);
  },
};

function CreateGlossaryDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () => glossaryApi.create({ name, description: description || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['glossaries'] });
      onCreated();
    },
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <Card className="w-full max-w-md animate-slide-up">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Create Glossary</CardTitle>
          <button onClick={onClose} className="text-foreground-muted hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
            className="space-y-4"
          >
            <Input
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Glossary"
              required
            />
            <Input
              label="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Technical terms for manufacturing"
            />
            <div className="flex gap-3 justify-end">
              <Button variant="secondary" type="button" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" isLoading={createMutation.isPending}>
                Create
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function GlossaryDetail({ glossary, onBack }: { glossary: Glossary; onBack: () => void }) {
  const [search, setSearch] = useState('');
  const [newSource, setNewSource] = useState('');
  const [newTarget, setNewTarget] = useState('');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['glossary-terms', glossary.id, search],
    queryFn: () => glossaryApi.listTerms(glossary.id, search || undefined),
  });

  const addMutation = useMutation({
    mutationFn: () => glossaryApi.addTerm(glossary.id, { source_term: newSource, target_term: newTarget }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['glossary-terms', glossary.id] });
      setNewSource('');
      setNewTarget('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (termId: string) => glossaryApi.deleteTerm(glossary.id, termId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['glossary-terms', glossary.id] });
    },
  });

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="sm" onClick={onBack}>
          ← Back
        </Button>
        <div>
          <h2 className="text-xl font-display font-bold text-foreground">{glossary.name}</h2>
          {glossary.description && (
            <p className="text-sm text-foreground-muted">{glossary.description}</p>
          )}
        </div>
      </div>

      {/* Add term form */}
      <Card className="mb-6">
        <CardContent className="py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (newSource && newTarget) {
                addMutation.mutate();
              }
            }}
            className="flex gap-4 items-end"
          >
            <div className="flex-1">
              <Input
                label="Korean Term"
                value={newSource}
                onChange={(e) => setNewSource(e.target.value)}
                placeholder="한국어 용어"
              />
            </div>
            <div className="flex-1">
              <Input
                label="English Translation"
                value={newTarget}
                onChange={(e) => setNewTarget(e.target.value)}
                placeholder="English term"
              />
            </div>
            <Button type="submit" isLoading={addMutation.isPending}>
              <Plus className="w-4 h-4 mr-2" />
              Add
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Search */}
      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground-subtle" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search terms..."
            className="w-full pl-10 pr-4 py-2 bg-background-tertiary border border-border rounded-md text-foreground placeholder-foreground-subtle focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </div>
      </div>

      {/* Terms table */}
      {isLoading ? (
        <div className="text-center py-12">
          <Loader2 className="w-8 h-8 text-accent animate-spin mx-auto" />
        </div>
      ) : data?.terms.length === 0 ? (
        <Card className="text-center py-12">
          <Book className="w-12 h-12 text-foreground-subtle mx-auto mb-4" />
          <p className="text-foreground">No terms yet</p>
          <p className="text-sm text-foreground-subtle">Add your first term above</p>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-4 text-sm font-medium text-foreground-muted">Korean</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-foreground-muted">English</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-foreground-muted">Confidence</th>
                  <th className="w-20"></th>
                </tr>
              </thead>
              <tbody>
                {data?.terms.map((term) => (
                  <tr key={term.id} className="border-b border-border/50 hover:bg-background-tertiary/50">
                    <td className="py-3 px-4 font-medium text-foreground">{term.source_term}</td>
                    <td className="py-3 px-4 text-foreground-muted">{term.target_term}</td>
                    <td className="py-3 px-4">
                      <span className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        term.confidence === 'high' && 'bg-success/10 text-success',
                        term.confidence === 'medium' && 'bg-warning/10 text-warning',
                        term.confidence === 'low' && 'bg-foreground-subtle/10 text-foreground-subtle',
                      )}>
                        {term.confidence}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <button
                        onClick={() => deleteMutation.mutate(term.id)}
                        className="p-1 text-foreground-subtle hover:text-danger"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function GlossariesPage() {
  const [showCreate, setShowCreate] = useState(false);
  const [selectedGlossary, setSelectedGlossary] = useState<Glossary | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['glossaries'],
    queryFn: glossaryApi.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => glossaryApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['glossaries'] });
    },
  });

  if (selectedGlossary) {
    return (
      <Layout>
        <GlossaryDetail glossary={selectedGlossary} onBack={() => setSelectedGlossary(null)} />
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-display font-bold text-foreground mb-2">Glossaries</h1>
          <p className="text-foreground-muted">Manage your translation terminology</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Glossary
        </Button>
      </div>

      {isLoading ? (
        <div className="text-center py-12">
          <Loader2 className="w-8 h-8 text-accent animate-spin mx-auto mb-4" />
          <p className="text-foreground-muted">Loading glossaries...</p>
        </div>
      ) : data?.glossaries.length === 0 ? (
        <Card className="text-center py-12">
          <Book className="w-12 h-12 text-foreground-subtle mx-auto mb-4" />
          <p className="text-foreground mb-2">No glossaries yet</p>
          <p className="text-sm text-foreground-subtle mb-6">
            Create a glossary to maintain consistent terminology
          </p>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Glossary
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data?.glossaries.map((glossary) => (
            <Card
              key={glossary.id}
              variant="hover"
              className="cursor-pointer"
              onClick={() => setSelectedGlossary(glossary)}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-accent/10 rounded-lg">
                    <Book className="w-5 h-5 text-accent" />
                  </div>
                  <div>
                    <h3 className="font-medium text-foreground">{glossary.name}</h3>
                    {glossary.description && (
                      <p className="text-sm text-foreground-subtle mt-1 line-clamp-2">
                        {glossary.description}
                      </p>
                    )}
                    <p className="text-sm text-foreground-muted mt-2">
                      {glossary.term_count} terms
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteMutation.mutate(glossary.id);
                  }}
                  className="p-1 text-foreground-subtle hover:text-danger"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateGlossaryDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => setShowCreate(false)}
        />
      )}
    </Layout>
  );
}

