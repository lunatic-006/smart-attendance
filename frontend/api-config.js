/**
 * API Configuration - Smart Attendance System
 * 
 * Supports both development and production environments
 * Automatically switches based on hostname
 */

// Detect environment
const isLocalFile = window.location.protocol === 'file:';
const isDevelopment = isLocalFile || 
                     window.location.hostname === 'localhost' || 
                     window.location.hostname === '127.0.0.1' || 
                     window.location.hostname === '';

// Get API URL based on environment
const getApiUrl = () => {
  // If we are looking at a file, default to localhost
  if (isLocalFile || window.location.hostname === '') {
    return 'http://localhost:8000/api';
  }
  
  // Otherwise, use the exact hostname we are connected to, but route to port 8000
  return `${window.location.protocol}//${window.location.hostname}:8000/api`;
};

// Export API configuration
const API_CONFIG = {
  URL: getApiUrl(),
  TIMEOUT: 30000, // 30 seconds
  RETRY_ATTEMPTS: 3,
  DEBUG: isDevelopment,
};

// Make it globally available
window.API_CONFIG = API_CONFIG;

// Log configuration in development
if (API_CONFIG.DEBUG) {
  console.log('🔧 API Configuration loaded:', API_CONFIG);
}
