(() => {
  const palette = [
    '#2563eb',
    '#f97316',
    '#14b8a6',
    '#8b5cf6',
    '#ef4444',
    '#facc15',
    '#22d3ee',
    '#10b981',
    '#ec4899',
    '#6366f1',
    '#0ea5e9',
    '#65a30d',
    '#d946ef',
    '#06b6d4',
    '#f59e0b',
    '#84cc16'
  ];

  function ready(handler) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', handler, { once: true });
    } else {
      handler();
    }
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  ready(() => {
    const formEl = document.querySelector('#semantic-graph-form');
    const termInput = document.querySelector('#semantic-term');
    const similarityInput = document.querySelector('#semantic-similarity');
    const maxNodesInput = document.querySelector('#semantic-max-nodes');
    const embeddingSelect = document.querySelector('#semantic-embedding');
    const randomBtn = document.querySelector('#semantic-random');
    const toggleButtons = Array.from(document.querySelectorAll('.viz-toggle button'));
    const forceStrengthInput = document.querySelector('#force-strength');
    const forceStrengthValue = document.querySelector('#force-strength-value');
    const rotateXInput = document.querySelector('#rotate-x');
    const rotateYInput = document.querySelector('#rotate-y');
    const rotateXValue = document.querySelector('#rotate-x-value');
    const rotateYValue = document.querySelector('#rotate-y-value');
    const fullscreenBtn = document.querySelector('#fullscreen-btn');
    const fullscreenIcon = document.querySelector('#fullscreen-icon');

    const graphShell = document.querySelector('.viz-graph-shell');
    const graph2DEl = document.querySelector('#semantic-graph-2d');
    const graph3DEl = document.querySelector('#semantic-graph-3d');
    const tooltipEl = document.querySelector('#semantic-tooltip');
    const legendEl = document.querySelector('#semantic-legend');

    if (!formEl || !graph2DEl || !graph3DEl || !tooltipEl) {
      console.warn('[Viz] Visualization controls missing from DOM.');
      return;
    }

    if (typeof ForceGraph !== 'function') {
      console.error('[Viz] ForceGraph library not loaded!');
      alert('Error: 2D graph library failed to load');
      return;
    }

    if (typeof ForceGraph3D !== 'function') {
      console.error('[Viz] ForceGraph3D library not loaded!');
      alert('Error: 3D graph library failed to load');
      return;
    }

    // Debug: Check if d3-force-3d loaded correctly
    console.log('[Viz] d3 object:', typeof d3, d3 ? Object.keys(d3).filter(k => k.includes('force')) : 'undefined');
    console.log('[Viz] Global THREE:', typeof THREE);
    console.log('[Viz] Global SpriteText:', typeof SpriteText);

    console.log('[Viz] All libraries loaded successfully');

    const state = {
      mode: '2d',
      currentTerm: '',
      forceStrength: Number(forceStrengthInput?.value ?? -160) || -160,
      rotationX: 0,
      rotationY: 0,
      colorMap: new Map(),
      legendEntries: [],
      tooltipVisible: false,
      pointer: { x: 0, y: 0 }
    };

    const assignColor = domain => {
      if (!domain) {
        domain = 'General';
      }
      if (!state.colorMap.has(domain)) {
        const index = state.colorMap.size % palette.length;
        state.colorMap.set(domain, palette[index]);
      }
      return state.colorMap.get(domain);
    };

    console.log('[Viz] Initializing 2D graph...');
    const Graph2D = ForceGraph()(graph2DEl)
      .nodeId('id')
      .backgroundColor('#f8fafc')
      .cooldownTicks(150)
      .nodeLabel(() => '')
      .nodeColor(node => node.__vizColor || '#2563eb')
      .nodeVal(node => {
        // Size based on rarity: rarer words (higher rarity) get bigger nodes
        // Scale from 4 (common) to 12 (rare)
        const rarity = node.final_rarity ?? 0.5;
        return 4 + (rarity * 8);
      })
      .linkWidth(link => Math.max(0.6, (link.value || 0) * 2))
      .linkColor(link => {
        // Make edge darkness more noticeable: higher similarity = darker edge
        // Range from 0.05 (very light/distant) to 0.95 (very dark/close)
        const similarity = link.value || 0;
        const opacity = 0.05 + (similarity * 0.9);
        return `rgba(14, 23, 42, ${opacity})`;
      });

    console.log('[Viz] Deferring 3D graph initialization until first use...');
    let Graph3D = null;

    function ensureGraph3D() {
      if (Graph3D) return Graph3D;

      console.log('[Viz] Initializing 3D graph now...', typeof ForceGraph3D);
      Graph3D = ForceGraph3D()(graph3DEl)
      .nodeId('id')
      .backgroundColor('#f8fafc')
      .cooldownTicks(180)
      .nodeLabel(node => {
        const parts = [
          `${node.term || 'Unknown'}`,
          node.part_of_speech ? `(${node.part_of_speech})` : '',
          node.primary_domain ? `Domain: ${node.primary_domain}` : '',
          typeof node.final_rarity === 'number' ? `Rarity: ${(node.final_rarity * 100).toFixed(1)} percentile` : ''
        ].filter(Boolean);
        return parts.join('\n');
      })
      .nodeColor(node => node.__vizColor || '#2563eb')
      .nodeVal(node => 6 + (node.degree || 0))
      .linkOpacity(0.3)
      .linkColor(link => `rgba(14, 23, 42, ${Math.min(0.2 + (link.value || 0) * 0.6, 0.85)})`)
      .linkDirectionalParticles(0);

      return Graph3D;
    }

    const charge2D = Graph2D.d3Force('charge');
    if (charge2D && typeof charge2D.strength === 'function') {
      charge2D.strength(state.forceStrength);
    }
    const link2D = Graph2D.d3Force('link');
    if (link2D && typeof link2D.distance === 'function') {
      link2D.distance(70);
    }

    // 3D force configuration will be applied when graph is first created

    Graph2D.nodeCanvasObjectMode(() => 'replace').nodeCanvasObject((node, ctx, globalScale) => {
      // Size based on rarity: rarer words get bigger nodes
      const rarity = node.final_rarity ?? 0.5;
      const radius = 4 + (rarity * 8); // Range from 4 to 12

      ctx.save();
      ctx.beginPath();
      ctx.fillStyle = node.__vizColor || '#2563eb';
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();

      // Keep bold outline for center node only
      if (node.is_center) {
        ctx.lineWidth = Math.max(1.5, 3 / globalScale);
        ctx.strokeStyle = '#0f172a';
        ctx.stroke();
      }

      const label = node.term || '';
      let box;
      if (label) {
        const fontSize = clamp(18 / globalScale, 11, 22);
        const paddingX = 6;
        const paddingY = 4;
        ctx.font = `${fontSize}px "Inter", "Segoe UI", sans-serif`;
        const textWidth = ctx.measureText(label).width;
        const boxWidth = textWidth + paddingX * 2;
        const boxHeight = fontSize + paddingY * 2;
        const boxX = node.x - boxWidth / 2;
        const boxY = node.y + radius + 6;

        ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
        ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
        ctx.strokeStyle = 'rgba(15, 23, 42, 0.12)';
        ctx.lineWidth = 1;
        ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);

        ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(label, node.x, boxY + paddingY);

        box = {
          x: boxX,
          y: boxY,
          width: boxWidth,
          height: boxHeight,
          radius
        };
      } else {
        box = {
          x: node.x - radius,
          y: node.y - radius,
          width: radius * 2,
          height: radius * 2,
          radius
        };
      }

      node.__labelBox = box;
      ctx.restore();
    });

    Graph2D.nodePointerAreaPaint((node, color, ctx) => {
      const box = node.__labelBox;
      const radius = box ? box.radius + 6 : Math.max(10, node.val + 6);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fill();
      if (box) {
        ctx.fillRect(box.x, box.y, box.width, box.height);
      }
    });

    function configure3DGraph(graph3D) {
      graph3D.nodeOpacity(1);
      graph3D.nodeThreeObject(node => {
        if (typeof SpriteText !== 'function' || !node.term) {
          return null;
        }
        const sprite = new SpriteText(node.term);
        sprite.color = '#0f172a';
        sprite.backgroundColor = 'rgba(255,255,255,0.9)';
        sprite.padding = 2;
        sprite.borderColor = 'rgba(15,23,42,0.45)';
        sprite.borderWidth = 0.6;
        sprite.textHeight = 8;
        // Position labels in front of nodes (positive Z moves toward camera)
        sprite.position.set(0, 0, 10);
        sprite.material.depthWrite = false;
        sprite.material.depthTest = false; // Always render in front
        return sprite;
      });
      graph3D.nodeThreeObjectExtend(true);

      const charge3D = graph3D.d3Force('charge');
      if (charge3D && typeof charge3D.strength === 'function') {
        charge3D.strength(state.forceStrength * 1.4);
      }
      const link3D = graph3D.d3Force('link');
      if (link3D && typeof link3D.distance === 'function') {
        link3D.distance(85);
      }

      const controls = graph3D.controls();
      if (controls) {
        controls.enablePan = false;
        controls.enableRotate = true;
        controls.enableZoom = true;
        controls.minPolarAngle = 0.05;
        controls.maxPolarAngle = Math.PI - 0.05;
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
      }
    }

    Graph2D.onEngineStop(() => {
      if (state.mode === '2d') {
        Graph2D.zoomToFit(300, 40);
      }
    });

    function updateForceStrengthDisplay() {
      if (forceStrengthValue) {
        forceStrengthValue.textContent = `${Math.round(state.forceStrength)}`;
      }
    }

    function updateRotationDisplay() {
      if (rotateXValue) {
        rotateXValue.textContent = `${Math.round((state.rotationX * 180) / Math.PI)}°`;
      }
      if (rotateYValue) {
        rotateYValue.textContent = `${Math.round((state.rotationY * 180) / Math.PI)}°`;
      }
    }

    function updateRotation() {
      if (!Graph3D || typeof Graph3D.scene !== 'function') {
        return;
      }
      const scene = Graph3D.scene();
      if (scene && scene.rotation) {
        scene.rotation.x = state.rotationX;
        scene.rotation.y = state.rotationY;
      }
    }

    function positionTooltip() {
      const rect = graphShell.getBoundingClientRect();
      const x = state.pointer.x - rect.left + 14;
      const y = state.pointer.y - rect.top + 14;
      tooltipEl.style.transform = `translate(${x}px, ${y}px)`;
    }

    function formatTooltip(node) {
      if (!node) {
        return '';
      }
      const rows = [
        `<div class="viz-tooltip-title">${node.term || 'Unknown term'}</div>`,
        node.part_of_speech ? `<div class="viz-tooltip-meta">${node.part_of_speech}</div>` : '',
        node.primary_domain ? `<div><strong>Domain:</strong> ${node.primary_domain}</div>` : '',
        typeof node.final_rarity === 'number'
          ? `<div><strong>Rarity:</strong> ${(node.final_rarity * 100).toFixed(1)} percentile</div>`
          : '',
        node.definition_excerpt ? `<div class="viz-tooltip-definition">${node.definition_excerpt}</div>` : ''
      ].filter(Boolean);
      return rows.join('');
    }

    function showTooltip(node) {
      const content = formatTooltip(node);
      if (!content) {
        hideTooltip();
        return;
      }
      tooltipEl.innerHTML = content;
      tooltipEl.style.opacity = '1';
      tooltipEl.dataset.visible = 'true';
      positionTooltip();
    }

    function hideTooltip() {
      tooltipEl.dataset.visible = 'false';
      tooltipEl.style.opacity = '0';
      tooltipEl.style.transform = 'translate(-9999px, -9999px)';
    }

    graphShell.addEventListener('pointermove', event => {
      state.pointer = { x: event.clientX, y: event.clientY };
      if (tooltipEl.dataset.visible === 'true') {
        positionTooltip();
      }
    });

    graphShell.addEventListener('pointerleave', hideTooltip);

    function handleHover(node) {
      if (node) {
        showTooltip(node);
      } else {
        hideTooltip();
      }
    }

    Graph2D.onNodeHover(handleHover);

    // Add click handler to make clicked node the new center
    Graph2D.onNodeClick((node) => {
      if (node && node.term && !node.is_center) {
        hideTooltip();
        termInput.value = node.term;
        state.currentTerm = node.term;
        fetchGraph({ term: node.term }).catch(error => {
          console.error('[Viz] Error recentering on node:', error);
          alert('Error loading graph: ' + error.message);
        });
      }
    });

    if (rotateXInput && rotateYInput) {
      const onRotationChange = () => {
        state.rotationX = (Number(rotateXInput.value) * Math.PI) / 180;
        state.rotationY = (Number(rotateYInput.value) * Math.PI) / 180;
        updateRotation();
        updateRotationDisplay();
      };
      rotateXInput.addEventListener('input', onRotationChange);
      rotateYInput.addEventListener('input', onRotationChange);
      onRotationChange();
    }

    if (forceStrengthInput) {
      const onForceChange = () => {
        const strength = Number(forceStrengthInput.value);
        if (!Number.isFinite(strength)) {
          return;
        }
        state.forceStrength = strength;
        updateForceStrengthDisplay();

        if (charge2D && typeof charge2D.strength === 'function') {
          charge2D.strength(strength);
        }
        if (Graph3D) {
          const charge3D = Graph3D.d3Force('charge');
          if (charge3D && typeof charge3D.strength === 'function') {
            charge3D.strength(strength * 1.4);
          }
        }
        if (typeof Graph2D.d3ReheatSimulation === 'function') {
          Graph2D.d3ReheatSimulation();
        }
        if (Graph3D && typeof Graph3D.d3ReheatSimulation === 'function') {
          Graph3D.d3ReheatSimulation();
        }
      };
      forceStrengthInput.addEventListener('input', onForceChange);
      onForceChange();
    }

    function ensureSize() {
      const isFullscreen = !!document.fullscreenElement;

      // In fullscreen, use full window dimensions
      // Otherwise, use container bounds
      if (isFullscreen) {
        const width = window.innerWidth;
        const height = window.innerHeight;
        Graph2D.width(width).height(height);
        if (Graph3D) {
          Graph3D.width(width).height(height);
        }
      } else {
        const rect = graphShell.getBoundingClientRect();
        const width = Math.max(rect.width || 800, 480);
        const height = Math.max(window.innerHeight * 0.55, 560);
        Graph2D.width(width).height(height);
        if (Graph3D) {
          Graph3D.width(width).height(height);
        }
      }
    }

    window.addEventListener('resize', () => {
      ensureSize();
      if (state.mode === '2d') {
        Graph2D.zoomToFit(300, 40);
      } else if (Graph3D) {
        Graph3D.zoomToFit(300, 80);
      }
    });

    function normalizeGraph(raw) {
      if (!raw || !Array.isArray(raw.nodes) || !Array.isArray(raw.edges)) {
        return { nodes: [], links: [] };
      }

      state.colorMap.clear();
      const domainCounts = new Map();

      const nodes = raw.nodes.map(node => {
        const domain = node.primary_domain || node.domain_name || 'General';
        const color = assignColor(domain);
        domainCounts.set(domain, (domainCounts.get(domain) || 0) + 1);
        return {
          ...node,
          id: node.id ?? node.term,
          __vizColor: color,
          degree: node.degree || 0
        };
      });

      const links = raw.edges.map(edge => ({
        source: edge.source,
        target: edge.target,
        value: typeof edge.similarity === 'number' ? edge.similarity : 0
      }));

      state.legendEntries = Array.from(domainCounts.entries())
        .map(([domain, count]) => ({
          domain,
          count,
          color: state.colorMap.get(domain)
        }))
        .sort((a, b) => b.count - a.count);

      return { nodes, links };
    }

    function updateMeta(raw) {
      // Update legend
      if (legendEl && state.legendEntries.length > 0) {
        const legendItems = state.legendEntries
          .map(entry => `
            <div class="viz-legend-item">
              <span class="viz-legend-swatch" style="background-color:${entry.color}"></span>
              <span class="viz-legend-label">${entry.domain}</span>
              <span class="viz-legend-count">${entry.count}</span>
            </div>
          `)
          .join('');

        legendEl.innerHTML = `
          <div class="viz-legend-title">Domains</div>
          <div class="viz-legend-items">
            ${legendItems}
          </div>
        `;
        legendEl.classList.add('visible');
      } else if (legendEl) {
        legendEl.classList.remove('visible');
      }
    }

    function applyGraph(raw) {
      const graphData = normalizeGraph(raw);

      Graph2D.graphData(graphData);
      if (typeof Graph2D.d3ReheatSimulation === 'function') {
        Graph2D.d3ReheatSimulation();
      }

      if (Graph3D) {
        Graph3D.graphData(graphData);
        if (typeof Graph3D.d3ReheatSimulation === 'function') {
          Graph3D.d3ReheatSimulation();
        }
      }

      ensureSize();
      Graph2D.zoomToFit(300, 40);
      if (Graph3D) {
        Graph3D.zoomToFit(300, 80);
      }
      updateRotation();

      updateMeta(raw);
    }

    async function fetchGraph(options = {}) {
      const params = new URLSearchParams();
      const term = options.term ?? termInput.value.trim();

      if (term) {
        params.set('term', term);
      }
      const similarity = clamp(Number(options.similarity ?? similarityInput.value) || 0.45, 0, 1);
      const maxNodes = clamp(parseInt(options.maxNodes ?? maxNodesInput.value, 10) || 32, 5, 150);

      params.set('similarity_floor', similarity.toString());
      params.set('max_nodes', maxNodes.toString());
      params.set('include_secondary_edges', 'true');

      const embedding = options.embedding ?? embeddingSelect.value;
      if (embedding) {
        params.set('embedding_model', embedding);
      }


      const response = await fetch(`/api/visualizations/word-graph?${params.toString()}`);
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed: ${response.status}`);
      }

      const payload = await response.json();
      state.currentTerm = payload?.center_word?.term || term || state.currentTerm;
      if (state.currentTerm) {
        termInput.value = state.currentTerm;
      }
      applyGraph(payload);
    }

    async function loadRandomTerm() {
      const response = await fetch('/api/random');
      if (!response.ok) {
        throw new Error(`Random word request failed (${response.status})`);
      }
      const payload = await response.json();
      const randomTerm = payload?.word?.term;
      if (!randomTerm) {
        throw new Error('Random word payload missing term');
      }
      termInput.value = randomTerm;
      state.currentTerm = randomTerm;
      await fetchGraph({ term: randomTerm });
    }

    formEl.addEventListener('submit', async event => {
      event.preventDefault();
      hideTooltip();
      try {
        await fetchGraph({});
      } catch (error) {
        console.error(error);
        alert('Error loading graph: ' + error.message);
      }
    });

    if (randomBtn) {
      randomBtn.addEventListener('click', async event => {
        event.preventDefault();
        hideTooltip();
        try {
          await loadRandomTerm();
        } catch (error) {
          console.error(error);
          alert('Error loading graph: ' + error.message);
        }
      });
    }

    toggleButtons.forEach(button => {
      button.addEventListener('click', () => {
        const mode = button.dataset.graphMode;
        if (!mode || mode === state.mode) {
          return;
        }
        state.mode = mode;
        hideTooltip();
        toggleButtons.forEach(btn => btn.classList.toggle('active', btn === button));

        if (mode === '2d') {
          graph2DEl.classList.remove('viz-hidden');
          graph3DEl.classList.add('viz-hidden');
          Graph2D.zoomToFit(300, 40);
        } else {
          // Initialize 3D graph on first switch to 3D mode
          const graph3D = ensureGraph3D();
          configure3DGraph(graph3D);

          // Set up event handlers for 3D graph
          graph3D.onEngineStop(() => {
            if (state.mode === '3d') {
              graph3D.zoomToFit(300, 80);
            }
          });
          graph3D.onNodeHover(handleHover);

          // Add click handler for 3D graph too
          graph3D.onNodeClick((node) => {
            if (node && node.term && !node.is_center) {
              hideTooltip();
              termInput.value = node.term;
              state.currentTerm = node.term;
              fetchGraph({ term: node.term }).catch(error => {
                console.error('[Viz] Error recentering on node:', error);
                alert('Error loading graph: ' + error.message);
              });
            }
          });

          // Copy current data to 3D graph
          const currentData = Graph2D.graphData();
          graph3D.graphData(currentData);

          graph3DEl.classList.remove('viz-hidden');
          graph2DEl.classList.add('viz-hidden');

          ensureSize();
          graph3D.zoomToFit(300, 80);
          updateRotation();
        }
      });
    });

    ensureSize();
    updateForceStrengthDisplay();
    updateRotationDisplay();

    // Fullscreen functionality
    if (fullscreenBtn) {
      fullscreenBtn.addEventListener('click', () => {
        const vizPage = document.querySelector('.viz-page');

        if (!document.fullscreenElement) {
          // Enter fullscreen
          if (vizPage.requestFullscreen) {
            vizPage.requestFullscreen();
          } else if (vizPage.webkitRequestFullscreen) {
            vizPage.webkitRequestFullscreen();
          } else if (vizPage.msRequestFullscreen) {
            vizPage.msRequestFullscreen();
          }
        } else {
          // Exit fullscreen
          if (document.exitFullscreen) {
            document.exitFullscreen();
          } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
          } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
          }
        }
      });

      // Update button text when fullscreen state changes
      document.addEventListener('fullscreenchange', () => {
        if (document.fullscreenElement) {
          fullscreenIcon.textContent = '⛶';
          fullscreenBtn.innerHTML = '<span id="fullscreen-icon">⛶</span> Exit Full Screen';
          // Resize graphs to fill fullscreen
          setTimeout(() => {
            ensureSize();
            if (state.mode === '2d') {
              Graph2D.zoomToFit(300, 40);
            } else if (Graph3D) {
              Graph3D.zoomToFit(300, 80);
            }
          }, 100);
        } else {
          fullscreenIcon.textContent = '⛶';
          fullscreenBtn.innerHTML = '<span id="fullscreen-icon">⛶</span> Full Screen';
          // Resize graphs back to normal
          setTimeout(() => {
            ensureSize();
            if (state.mode === '2d') {
              Graph2D.zoomToFit(300, 40);
            } else if (Graph3D) {
              Graph3D.zoomToFit(300, 80);
            }
          }, 100);
        }
      });
    }

    const initialTerm = termInput.value.trim();
    console.log('[Viz] Initial term:', initialTerm);

    if (initialTerm) {
      console.log('[Viz] Loading graph for:', initialTerm);
      fetchGraph({ term: initialTerm }).catch(error => {
        console.error('[Viz] Error loading graph:', error);
        alert('Error loading graph: ' + error.message);
      });
    } else {
      console.log('[Viz] Loading random term...');
      loadRandomTerm().catch(error => {
        console.error('[Viz] Error loading random:', error);
        alert('Error loading random term: ' + error.message);
      });
    }
  });
})();
