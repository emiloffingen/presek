import { cyrToLat, latToCyr } from '../utils/textUtils';
if (typeof window !== 'undefined') {
	window.cyrToLat = cyrToLat;
	window.latToCyr = latToCyr;
}
