import 'pdbe-molstar/build/pdbe-molstar.css';
import { ThemeContext } from '../main.jsx';
import { useRef, useContext, useEffect, useState } from 'react';

export default function PdbViewer({ tcrId }) {
    const viewerRef = useRef(null);
    const pluginRef = useRef(null);
    const { isDark } = useContext(ThemeContext);

    useEffect(() => {
        let isMounted = true;

        const initViewer = async () => {
            if (!viewerRef.current) return;

            // Dynamically import to avoid SSR issues or global scope pollution if any
            // pdbe-molstar adds PDBeMolstarPlugin to window if imported this way
            await import('pdbe-molstar/build/pdbe-molstar-plugin.js');

            if (!isMounted) return;

            const plugin = new window.PDBeMolstarPlugin();
            pluginRef.current = plugin;

            const options = {
                customData: {
                    url: `http://localhost:3001/data/predictions/boltz2/result-${tcrId}/predictions/result/result_model_0.pdb`,
                    format: 'pdb',
                },
                bgColor: isDark ? { r: 10, g: 12, b: 18 } : { r: 220, g: 220, b: 220 }, // Matches var(--bg-surface) for light and dark
                highlightColor: isDark ? { r: 10, g: 12, b: 18 } : { r: 220, g: 220, b: 220 },
                selectColor: isDark ? { r: 10, g: 12, b: 18 } : { r: 220, g: 220, b: 220 },
                moleculeId: 'result_model_0.pdb',
                hideControls: true,
                hideExpandIcon: true,
                hideControlWindow: true,
                hideSequence: true,
                hideAnimation: true,
                hideWater: true,
                landscape: false,
                visualStyle: 'cartoon',
                lighting: 'flat', // cleaner lighting for this UI
            };

            plugin.render(viewerRef.current, options);
        };

        initViewer();

        return () => {
            isMounted = false;
            // Best effort cleanup if the plugin supports it
            if (pluginRef.current && typeof pluginRef.current.clear === 'function') {
                pluginRef.current.clear();
            }
        };
    }, [tcrId, isDark]);

    return (
        <div style={{
            width: '100%',
            height: '280px',
            position: 'relative',
            borderRadius: 8,
            overflow: 'hidden',
            border: '1px solid var(--border-strong)',
            background: 'var(--bg-base)',
            boxShadow: 'inset 0 0 20px rgba(0,0,0,0.2)'
        }}>
            <div ref={viewerRef} style={{ width: '100%', height: '100%' }} />
        </div>
    );
}
