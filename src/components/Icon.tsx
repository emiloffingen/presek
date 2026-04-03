import React from 'react';
import * as Icons from 'lucide-react';

type IconName = keyof typeof Icons;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

export const Icon: React.FC<IconProps> = ({ name, size = 20, className = '' }) => {
  const IconComponent = Icons[name] as React.ComponentType<any>;
  if (!IconComponent) return null;
  
  return <IconComponent size={size} className={className} />;
};
