import { FileQuestion, Home } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';

/**
 * NotFound page - 404 error page for invalid routes.
 */
export default function NotFoundPage() {
  return (
    <div className='flex min-h-[60vh] flex-col items-center justify-center px-6 py-16'>
      <div className='text-center'>
        {/* Icon */}
        <div className='bg-syft-surface mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full'>
          <FileQuestion className='text-syft-muted h-10 w-10' />
        </div>

        {/* Title */}
        <h1 className='font-rubik text-syft-primary mb-2 text-4xl font-semibold'>404</h1>
        <h2 className='font-rubik text-syft-primary mb-4 text-xl font-medium'>Page Not Found</h2>

        {/* Description */}
        <p className='font-inter text-syft-muted mx-auto mb-8 max-w-md'>
          The page you're looking for doesn't exist or has been moved. Check the URL or head back to
          the home page.
        </p>

        {/* Action */}
        <Link to='/'>
          <Button size='lg' className='font-inter'>
            <Home className='mr-2 h-4 w-4' />
            Back to Home
          </Button>
        </Link>
      </div>
    </div>
  );
}
