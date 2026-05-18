import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Users from 'lucide-react/dist/esm/icons/users';
import Check from 'lucide-react/dist/esm/icons/check';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface CollectiveFormData {
  // Basic Info
  name: string;
  slug: string;
  description: string;
  avatarUrl?: string;
  bannerUrl?: string;
  
  // Membership
  membershipVisibility: 'open' | 'request' | 'invite-only';
  
  // Hosting
  supportsHosting: boolean;
}


export default function CreateCollectivePage() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<CollectiveFormData>({
    name: '',
    slug: '',
    description: '',
    membershipVisibility: 'request',
    supportsHosting: false,
  });

  const steps = [
    { id: 1, name: 'Basic Information', icon: Users },
    { id: 2, name: 'Membership', icon: Shield },
    { id: 3, name: 'Review', icon: Check },
  ];

  const handleNext = () => {
    if (currentStep < steps.length) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleCreate = () => {
    console.log('Creating collective:', formData);
    // In real implementation, this would create the collective in the backend
    // For now, just redirect to the admin page
    navigate(`/c/${formData.slug}/admin`);
  };

  const updateFormData = (updates: Partial<CollectiveFormData>) => {
    setFormData(prev => ({ ...prev, ...updates }));
  };

  const generateSlug = (name: string) => {
    return name.toLowerCase()
      .replace(/\s+/g, '-')  // Replace spaces with hyphens
      .replace(/[^a-z0-9-]/g, '')  // Remove non-alphanumeric characters except hyphens
      .replace(/-+/g, '-')  // Replace multiple hyphens with single hyphen
      .replace(/^-|-$/g, '');  // Remove leading and trailing hyphens
  };

  return (
    <div className="container mx-auto px-6 py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <Link to="/collectives" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4">
          <ArrowLeft className="w-4 h-4" />
          Back to Collectives
        </Link>
        
        <h1 className="text-3xl font-bold">Create a Collective</h1>
        <p className="text-muted-foreground mt-1">
          Build a community around shared data and infrastructure
        </p>
      </div>

      {/* Progress Steps */}
      <div className="flex items-center justify-between mb-8">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const isActive = step.id === currentStep;
          const isCompleted = step.id < currentStep;
          
          return (
            <div key={step.id} className="flex items-center flex-1">
              <div className="flex items-center">
                <div
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center",
                    isActive && "bg-primary text-primary-foreground",
                    isCompleted && "bg-primary/20 text-primary",
                    !isActive && !isCompleted && "bg-muted text-muted-foreground"
                  )}
                >
                  {isCompleted ? (
                    <Check className="w-5 h-5" />
                  ) : (
                    <Icon className="w-5 h-5" />
                  )}
                </div>
                <div className="ml-3">
                  <p className={cn(
                    "text-sm font-medium",
                    isActive && "text-foreground",
                    !isActive && "text-muted-foreground"
                  )}>
                    {step.name}
                  </p>
                </div>
              </div>
              {index < steps.length - 1 && (
                <div className={cn(
                  "flex-1 h-0.5 mx-4",
                  isCompleted ? "bg-primary/20" : "bg-muted"
                )} />
              )}
            </div>
          );
        })}
      </div>

      {/* Form Content */}
      <Card className="p-6">
        {currentStep === 1 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold mb-4">Basic Information</h2>
            
            <div>
              <Label htmlFor="name">Collective Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => {
                  updateFormData({ 
                    name: e.target.value,
                    slug: generateSlug(e.target.value)
                  });
                }}
                placeholder="e.g., Harvard Medical Collective"
                className="mt-1"
              />
            </div>

            <div>
              <Label htmlFor="slug">URL Slug *</Label>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-muted-foreground">syfthub.ai/c/</span>
                <Input
                  id="slug"
                  value={formData.slug}
                  onChange={(e) => updateFormData({ slug: e.target.value })}
                  placeholder="harvard-medical"
                  className="flex-1"
                />
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                This cannot be changed later
              </p>
            </div>

            <div>
              <Label htmlFor="description">README *</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => updateFormData({ description: e.target.value })}
                placeholder="# About Our Collective\n\nDescribe your collective's mission and what types of data you'll share...\n\n## Members\n\n## Data Types\n\n## How to Join"
                rows={10}
                className="mt-1 font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Supports markdown formatting for rich documentation
              </p>
            </div>

            <div>
              <Label htmlFor="avatar">Logo URL (optional)</Label>
              <Input
                id="avatar"
                value={formData.avatarUrl}
                onChange={(e) => updateFormData({ avatarUrl: e.target.value })}
                placeholder="https://example.com/logo.png"
                className="mt-1"
              />
            </div>
            
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <Label htmlFor="hosting">Supports hosting for members</Label>
                <p className="text-sm text-muted-foreground mt-1">
                  Enable if your collective will provide infrastructure and hosting services for member endpoints
                </p>
              </div>
              <Switch
                id="hosting"
                checked={formData.supportsHosting}
                onCheckedChange={(checked) => updateFormData({ supportsHosting: checked })}
              />
            </div>
          </div>
        )}

        {currentStep === 2 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold mb-4">Membership Settings</h2>
            
            <div>
              <Label>Who can join your collective?</Label>
              <div className="grid grid-cols-1 gap-3 mt-3">
                {(['open', 'request', 'invite-only'] as const).map((type) => (
                  <Card
                    key={type}
                    className={cn(
                      "p-4 cursor-pointer transition-colors",
                      formData.membershipVisibility === type && "ring-2 ring-primary"
                    )}
                    onClick={() => updateFormData({ membershipVisibility: type })}
                  >
                    <div className="flex items-start gap-3">
                      <div className={cn(
                        "w-4 h-4 rounded-full border-2 mt-0.5",
                        formData.membershipVisibility === type
                          ? "border-primary bg-primary"
                          : "border-muted-foreground"
                      )}>
                        {formData.membershipVisibility === type && (
                          <div className="w-2 h-2 bg-white rounded-full m-0.5" />
                        )}
                      </div>
                      <div>
                        <p className="font-medium capitalize">{type.replace('-', ' ')}</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {type === 'open' && 'Anyone can join immediately without approval'}
                          {type === 'request' && 'Users can request to join, pending admin approval'}
                          {type === 'invite-only' && 'Only invited users can join'}
                        </p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          </div>
        )}

        {currentStep === 3 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold mb-4">Review & Create</h2>
            
            <div className="space-y-4">
              <div className="p-4 bg-muted/50 rounded-lg">
                <h3 className="font-medium mb-3">Basic Information</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Name:</span>
                    <span className="font-medium">{formData.name || 'Not set'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">URL:</span>
                    <span className="font-medium">syfthub.ai/c/{formData.slug || '...'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Membership:</span>
                    <Badge variant="outline">{formData.membershipVisibility}</Badge>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-muted/50 rounded-lg">
                <h3 className="font-medium mb-3">Hosting</h3>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Supports member hosting:</span>
                  <Badge variant={formData.supportsHosting ? "default" : "outline"}>
                    {formData.supportsHosting ? 'Yes' : 'No'}
                  </Badge>
                </div>
              </div>
            </div>

            <div className="p-4 bg-green-500/10 text-green-600 rounded-lg">
              <p className="text-sm">
                ✓ Your collective will be created and you'll be redirected to the admin dashboard
              </p>
            </div>
          </div>
        )}
      </Card>

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-6">
        {currentStep > 1 ? (
          <Button variant="outline" onClick={handleBack}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
        ) : (
          <Link to="/collectives">
            <Button variant="outline">Cancel</Button>
          </Link>
        )}

        {currentStep < steps.length ? (
          <Button 
            onClick={handleNext}
            disabled={
              (currentStep === 1 && (!formData.name || !formData.slug || !formData.description))
            }
          >
            Next
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        ) : (
          <Button onClick={handleCreate} className="bg-green-600 hover:bg-green-700">
            <Check className="w-4 h-4 mr-2" />
            Create Collective
          </Button>
        )}
      </div>
    </div>
  );
}