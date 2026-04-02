# ─────────────────────────────────────────────────────────────────────────
    #  Generación mejorada de fondo (realista + asientos visualizados)
    # ─────────────────────────────────────────────────────────────────────────

def _draw_background_improved(self):
        """
        Genera QPixmap 1920×1080 que simula sala de conferencias real.
        
        MEJORAS vs versión simple:
          • Gradiente de iluminación (realista)
          • Asientos visualizados como círculos azules
          • Podio presidencial con símbolo ⚜️
          • 3 secciones diferenciadas con etiquetas
          • Filas traseras (Back Rows) con patrón visual
          • Zonas especiales con marcos decorativos
          • Arquitectura: columnas, marcos, líneas de piso
          • Leyenda visual abajo
        
        ESTRUCTURA:
          1. Fondo base + gradiente (simulando iluminación teatral)
          2. Patrón de piso (cuadrícula sutil)
          3. Escenario/Plataforma (podio + Chairman + Left/Right)
          4. Público (3 secciones con asientos visuales)
          5. Filas traseras (Row 7-9)
          6. Zonas especiales (Wheelchair, Remote Room)
          7. Decoración arquitectónica (columnas, marcos)
          8. Leyenda informativa
        """
        pixmap = QPixmap(1920, 1080)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        
        # ────────────────────────────────────────────────────────────────────
        #  1. FONDO BASE + GRADIENTE DE ILUMINACIÓN
        # ────────────────────────────────────────────────────────────────────
        # Gradiente vertical: superior más claro (iluminación) → inferior oscuro
        pixmap.fill(QColor(70, 70, 75))
        
        gradient = QtGui.QLinearGradient(0, 0, 0, 1080)
        gradient.setColorAt(0, QColor(180, 180, 185))      # Superior (escenario)
        gradient.setColorAt(0.3, QColor(140, 140, 145))    # Transición
        gradient.setColorAt(0.7, QColor(90, 90, 95))       # Inferior (público)
        
        painter.fillRect(0, 0, 1920, 1080, gradient)
        
        # ────────────────────────────────────────────────────────────────────
        #  2. PATRÓN DE PISO (cuadrícula sutil = realismo)
        # ────────────────────────────────────────────────────────────────────
        # Líneas cada 80px simulan patrón de baldosas
        painter.setPen(QtGui.QPen(QColor(100, 100, 105), 1, Qt.DotLine))
        for y in range(0, 1080, 80):
            painter.drawLine(0, y, 1920, y)
        for x in range(0, 1920, 80):
            painter.drawLine(x, 0, x, 1080)
        
        # ────────────────────────────────────────────────────────────────────
        #  3. ESCENARIO / PLATAFORMA (superior, y=0-140)
        # ────────────────────────────────────────────────────────────────────
        # Zona más clara donde están Chairman, Left, Right
        painter.fillRect(0, 0, 1920, 140, QColor(160, 160, 165))
        
        # Borde superior (marco escenario)
        painter.setPen(QtGui.QPen(QColor(40, 40, 45), 4))
        painter.drawLine(0, 0, 1920, 0)
        
        # Línea separadora escenario/público
        painter.setPen(QtGui.QPen(QColor(100, 100, 105), 2))
        painter.drawLine(0, 140, 1920, 140)
        
        # PODIO PRESIDENCIAL (centro superior)
        podium_x, podium_y = 860, 20
        podium_w, podium_h = 200, 80
        
        # Relleno podio (madera oscura)
        painter.fillRect(podium_x, podium_y, podium_w, podium_h, 
                        QColor(120, 100, 80))
        
        # Borde podio
        painter.setPen(QtGui.QPen(QColor(60, 50, 40), 3))
        painter.drawRect(podium_x, podium_y, podium_w, podium_h)
        
        # Símbolo presidencia (⚜️)
        painter.setPen(QColor(200, 180, 100))
        painter.setFont(QtGui.QFont("Arial", 36, QtGui.QFont.Bold))
        painter.drawText(podium_x, podium_y - 5, podium_w, podium_h + 20,
                        QtCore.Qt.AlignCenter, "⚜️")
        
        # Etiquetas posiciones plataforma
        painter.setPen(QColor(40, 40, 50))
        painter.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        painter.drawText(860, 110, 200, 25, QtCore.Qt.AlignCenter, "CHAIRMAN")
        painter.drawText(400, 110, 150, 25, QtCore.Qt.AlignCenter, "LEFT")
        painter.drawText(1370, 110, 150, 25, QtCore.Qt.AlignCenter, "RIGHT")
        
        # ────────────────────────────────────────────────────────────────────
        #  4. SECCIONES DE PÚBLICO (3 zonas con asientos visuales)
        # ────────────────────────────────────────────────────────────────────
        # Dibuja pequeños círculos (●) para representar asientos
        
        def draw_section(x_start, y_start, rows, cols, label):
            """Dibuja una sección de asientos con círculos azules."""
            seat_radius = 4
            spacing_x = 50
            spacing_y = 50
            
            # Fondo sección (diferenciado)
            painter.fillRect(x_start - 20, y_start - 20,
                            cols * spacing_x + 40, rows * spacing_y + 40,
                            QColor(100, 100, 105))
            
            # Borde sección
            painter.setPen(QtGui.QPen(QColor(130, 130, 135), 2, Qt.DashLine))
            painter.drawRect(x_start - 20, y_start - 20,
                            cols * spacing_x + 40, rows * spacing_y + 40)
            
            # Asientos como círculos azules
            painter.setPen(QtGui.QPen(QColor(60, 100, 140), 1))
            painter.setBrush(QtGui.QBrush(QColor(100, 150, 180)))
            
            for row in range(rows):
                for col in range(cols):
                    x = x_start + col * spacing_x
                    y = y_start + row * spacing_y
                    painter.drawEllipse(x - seat_radius, y - seat_radius,
                                       seat_radius * 2, seat_radius * 2)
            
            # Etiqueta sección
            painter.setPen(QColor(180, 180, 185))
            painter.setFont(QtGui.QFont("Arial", 11, QtGui.QFont.Bold))
            label_x = x_start + (cols * spacing_x) // 2 - 40
            label_y = y_start - 35
            painter.drawText(label_x, label_y, 80, 20,
                            QtCore.Qt.AlignCenter, label)
        
        # SECCIÓN IZQUIERDA (6 filas × 4 columnas = 24 asientos)
        draw_section(100, 180, 6, 4, "IZQUIERDA")
        
        # SECCIÓN CENTRAL (6 filas × 5 columnas = 30 asientos)
        draw_section(650, 180, 6, 5, "CENTRAL")
        
        # SECCIÓN DERECHA (6 filas × 4 columnas = 24 asientos)
        draw_section(1200, 180, 6, 4, "DERECHA")
        
        # ────────────────────────────────────────────────────────────────────
        #  5. FILAS TRASERAS (Back Rows 7-9)
        # ────────────────────────────────────────────────────────────────────
        painter.setPen(QColor(150, 150, 155))
        painter.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))
        painter.drawText(700, 750, 500, 30, QtCore.Qt.AlignCenter,
                        "BACK ROWS (7-9)")
        
        # Primera línea de back row
        painter.setPen(QtGui.QPen(QColor(80, 120, 150), 1))
        painter.setBrush(QtGui.QBrush(QColor(120, 160, 190)))
        
        back_row_y = 800
        for x in range(200, 1700, 40):
            painter.drawEllipse(x - 5, back_row_y - 5, 10, 10)
        
        # Segunda línea de back row
        back_row_y2 = 870
        for x in range(200, 1700, 40):
            painter.drawEllipse(x - 5, back_row_y2 - 5, 10, 10)
        
        # ────────────────────────────────────────────────────────────────────
        #  6. ZONAS ESPECIALES (abajo)
        # ────────────────────────────────────────────────────────────────────
        
        # WHEELCHAIR ACCESSIBILITY (izquierda)
        painter.setPen(QColor(180, 140, 100))
        painter.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        painter.drawText(100, 980, 200, 50, QtCore.Qt.AlignCenter,
                        "♿\nWHEELCHAIR")
        
        # Marco zona accesible
        painter.setPen(QtGui.QPen(QColor(200, 160, 120), 2, Qt.DashLine))
        painter.drawRect(50, 950, 300, 80)
        
        # REMOTE ROOM (derecha)
        painter.setPen(QColor(180, 140, 100))
        painter.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        painter.drawText(1620, 980, 200, 50, QtCore.Qt.AlignCenter,
                        "🖥️\nREMOTE ROOM")
        
        # Marco sala remota
        painter.setPen(QtGui.QPen(QColor(200, 160, 120), 2, Qt.DashLine))
        painter.drawRect(1570, 950, 300, 80)
        
        # ────────────────────────────────────────────────────────────────────
        #  7. DECORACIÓN ARQUITECTÓNICA (columnas, marcos)
        # ────────────────────────────────────────────────────────────────────
        
        # Columnas laterales (efecto 3D/profundidad)
        painter.setPen(QtGui.QPen(QColor(50, 50, 55), 8))
        painter.drawLine(50, 140, 50, 950)      # Columna izq
        painter.drawLine(1870, 140, 1870, 950)  # Columna der
        
        # Marco perimetral general (borde pantalla)
        painter.setPen(QtGui.QPen(QColor(80, 80, 85), 3))
        painter.drawRect(0, 0, 1920, 1080)
        
        # Línea horizontal de división visual (mitad)
        painter.setPen(QtGui.QPen(QColor(100, 100, 110), 2, Qt.DashLine))
        painter.drawLine(100, 500, 1820, 500)
        
        # ────────────────────────────────────────────────────────────────────
        #  8. LEYENDA VISUAL (abajo)
        # ────────────────────────────────────────────────────────────────────
        painter.setPen(QColor(120, 120, 125))
        painter.setFont(QtGui.QFont("Arial", 9))
        painter.drawText(700, 1040, 500, 30, QtCore.Qt.AlignCenter,
                        "● = Seat | ⚜️ = Chairman | ♿ = Wheelchair | 🖥️ = Remote")
        
        painter.end()
        return pixmap