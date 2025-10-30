import sqlite3
import os
import struct
import sys
from tkinter import filedialog, messagebox, Canvas
from customtkinter import *

# --- Constantes e Configuração ---
CONFIG_DB = 'msx_font_editor.db'
DEFAULT_FONT_PATH_KEY = 'fonte_padrao_caminho'


# --- Funções de Configuração SQLite ---

def setup_config():
    """Configura o banco de dados SQLite e garante a configuração inicial (caminho da fonte)."""

    # Inicializa o CustomTkinter para usar as caixas de diálogo
    root = CTk()
    root.withdraw()  # Esconde a janela principal do CustomTkinter

    try:
        conn = sqlite3.connect(CONFIG_DB)
        cursor = conn.cursor()

        # Cria a tabela de configuração
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS configuracao
                       (
                           opcao
                           TEXT
                           PRIMARY
                           KEY,
                           valor
                           TEXT
                       )
                       ''')
        conn.commit()

        # Tenta obter o caminho da fonte padrão
        cursor.execute('SELECT valor FROM configuracao WHERE opcao=?', (DEFAULT_FONT_PATH_KEY,))
        result = cursor.fetchone()

        if result is None:
            # Solicita o caminho da fonte ao usuário se não estiver configurado
            messagebox.showinfo("Configuração Inicial",
                                "O arquivo de configuração não foi encontrado ou está incompleto. Por favor, selecione o arquivo de fonte (.ALF) padrão do MSX (formato Graphos III).")

            while True:
                default_path = filedialog.askopenfilename(
                    title="Selecione a Fonte Padrão (.ALF)",
                    filetypes=[("Arquivos de Alfabeto MSX", "*.ALF"), ("Todos os arquivos", "*.*")]
                )
                if default_path:
                    # Salva o caminho
                    cursor.execute('INSERT OR REPLACE INTO configuracao (opcao, valor) VALUES (?, ?)',
                                   (DEFAULT_FONT_PATH_KEY, default_path))
                    conn.commit()
                    conn.close()
                    root.destroy()
                    return default_path
                else:
                    if not messagebox.askretrycancel("Erro de Configuração",
                                                     "O caminho da fonte padrão é obrigatório para iniciar o editor. Tentar novamente?"):
                        root.destroy()
                        sys.exit("Configuração inicial cancelada pelo usuário.")
        else:
            conn.close()
            path = result[0]
            root.destroy()
            return path

    except Exception as e:
        root.destroy()
        messagebox.showerror("Erro de Inicialização", f"Ocorreu um erro no setup: {e}")
        sys.exit()


def set_config(key, value):
    """Salva ou atualiza um valor de configuração."""
    conn = sqlite3.connect(CONFIG_DB)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO configuracao (opcao, valor) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()


# --- Classe de Manipulação de Arquivo .ALF (Graphos III) ---

class MSXFont:
    """Representa o alfabeto MSX e manipula a leitura/escrita do formato .ALF."""

    HEADER_SIZE = 7
    CHAR_SIZE = 8
    NUM_CHARS = 256
    DATA_SIZE = NUM_CHARS * CHAR_SIZE
    FILE_SIZE = HEADER_SIZE + DATA_SIZE

    # Cabeçalho padrão do Graphos III
    DEFAULT_HEADER = struct.pack('<BHHH', 0xFE, 0x9200, 0x99FF, 0x9200)

    def __init__(self, filepath):
        self.filepath = filepath
        self.chars = self._load_font()
        self.modified_chars = set()

    def _load_font(self):
        """Carrega a fonte do arquivo .ALF, validando o cabeçalho e o tamanho."""
        if not os.path.exists(self.filepath):
            empty_data = bytearray(self.DATA_SIZE)
            messagebox.showwarning("Aviso", f"Arquivo de fonte '{self.filepath}' não encontrado. Criando fonte vazia.")
            return [empty_data[i:i + self.CHAR_SIZE] for i in range(0, self.DATA_SIZE, self.CHAR_SIZE)]

        with open(self.filepath, 'rb') as f:
            content = f.read()

        if len(content) != self.FILE_SIZE:
            messagebox.showerror("Erro",
                                 f"Tamanho de arquivo inválido: {len(content)} bytes. Esperado: {self.FILE_SIZE} bytes.")
            empty_data = bytearray(self.DATA_SIZE)
            return [empty_data[i:i + self.CHAR_SIZE] for i in range(0, self.DATA_SIZE, self.CHAR_SIZE)]

        header = content[:self.HEADER_SIZE]
        if header != self.DEFAULT_HEADER:
            messagebox.showwarning("Aviso",
                                   "O cabeçalho do arquivo não corresponde ao padrão Graphos III ($9200-$99FF). O arquivo será lido, mas a gravação usará o cabeçalho padrão.")

        data = bytearray(content[self.HEADER_SIZE:])
        return [data[i:i + self.CHAR_SIZE] for i in range(0, self.DATA_SIZE, self.CHAR_SIZE)]

    def get_char_pattern(self, ascii_code):
        """Retorna os 8 bytes de um caractere."""
        if 0 <= ascii_code < self.NUM_CHARS:
            return self.chars[ascii_code]
        return None

    def update_char_pattern(self, ascii_code, new_pattern):
        """Atualiza o padrão de 8 bytes de um caractere e marca como modificado."""
        if 0 <= ascii_code < self.NUM_CHARS and len(new_pattern) == self.CHAR_SIZE:
            self.chars[ascii_code] = bytearray(new_pattern)
            self.modified_chars.add(ascii_code)

    def save(self, filepath=None):
        """Salva a fonte no formato Graphos III (.ALF)."""
        if filepath is None:
            filepath = self.filepath

        try:
            with open(filepath, 'wb') as f:
                f.write(self.DEFAULT_HEADER)
                for char_pattern in self.chars:
                    f.write(char_pattern)

            self.filepath = filepath
            self.modified_chars.clear()
            messagebox.showinfo("Sucesso", f"Fonte salva em: {filepath}")
            return True
        except Exception as e:
            messagebox.showerror("Erro de Gravação", f"Não foi possível salvar o arquivo: {e}")
            return False


# --- Janela de Edição 8x8 (CTkTopLevel) ---

class EditorWindow(CTkToplevel):
    """Janela de edição 8x8 de um caractere."""

    # Cores
    COLOR_BG = '#1e1e1e'
    COLOR_PIXEL_ON = '#ffffff'
    COLOR_PIXEL_OFF = '#303030'
    COLOR_CURSOR = '#1F6AA5'

    def __init__(self, master, char_code, pattern, callback):
        self.char_code = char_code
        self.callback = callback
        self.pixel_data = [[(pattern[row] >> (7 - col)) & 1 for col in range(8)] for row in range(8)]
        self.pixel_size = 40  # Mantenha o editor grande para facilitar a precisão

        super().__init__(master)
        self.title(f"Editor de Caractere: 0x{char_code:02X} ('{chr(char_code) if 32 <= char_code <= 126 else ' '}')")
        self.configure(fg_color=self.COLOR_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        # Frame para conter o canvas
        editor_frame = CTkFrame(self, fg_color=self.COLOR_BG)
        editor_frame.pack(padx=10, pady=10)

        self.editor_canvas = Canvas(editor_frame, width=8 * self.pixel_size, height=8 * self.pixel_size,
                                    bg=self.COLOR_BG, highlightthickness=1, highlightbackground=self.COLOR_PIXEL_ON)
        self.editor_canvas.pack(padx=1, pady=1)

        self.cursor_row, self.cursor_col = 0, 0

        # Bindings
        self.editor_canvas.bind('<Button-1>', self.on_click)
        self.editor_canvas.bind('<Button-3>', self.save_and_close)
        self.bind('<Return>', self.save_and_close)
        self.bind('<space>', self.toggle_current_pixel)
        self.bind('<Key>', self.on_key_press)

        self.protocol("WM_DELETE_WINDOW", self.cancel_and_close)

        self.draw_editor()
        self.draw_editor_cursor()

    def draw_editor(self):
        """Desenha a grade 8x8 e os pixels."""
        self.editor_canvas.delete("pixels")

        for r in range(8):
            for c in range(8):
                x1, y1 = c * self.pixel_size, r * self.pixel_size
                x2, y2 = x1 + self.pixel_size, y1 + self.pixel_size

                color = self.COLOR_PIXEL_ON if self.pixel_data[r][c] == 1 else self.COLOR_PIXEL_OFF

                self.editor_canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline=self.COLOR_PIXEL_OFF, width=1,
                                                    tags="pixels")

    def draw_editor_cursor(self):
        """Desenha o cursor de navegação 8x8."""
        self.editor_canvas.delete("editor_cursor")

        r, c = self.cursor_row, self.cursor_col
        x1, y1 = c * self.pixel_size, r * self.pixel_size
        x2, y2 = x1 + self.pixel_size, y1 + self.pixel_size

        self.editor_canvas.create_rectangle(x1, y1, x2, y2, outline=self.COLOR_CURSOR, width=3, tags="editor_cursor")

    def move_editor_cursor(self, dx, dy):
        """Move o cursor na grade 8x8."""
        self.cursor_row = (self.cursor_row + dy) % 8
        self.cursor_col = (self.cursor_col + dx) % 8
        self.draw_editor_cursor()

    def toggle_pixel(self, r, c):
        """Inverte o estado do pixel e redesenha."""
        self.pixel_data[r][c] = 1 - self.pixel_data[r][c]
        self.draw_editor()
        self.draw_editor_cursor()

    def toggle_current_pixel(self, event=None):
        """Inverte o pixel sob o cursor."""
        self.toggle_pixel(self.cursor_row, self.cursor_col)

    def on_click(self, event):
        """Trata o clique do mouse na grade 8x8 (inverte o pixel)."""
        r = event.y // self.pixel_size
        c = event.x // self.pixel_size

        if 0 <= r < 8 and 0 <= c < 8:
            self.cursor_row, self.cursor_col = r, c
            self.toggle_pixel(r, c)

    def on_key_press(self, event):
        """Trata as teclas de seta e outras teclas."""
        if event.keysym == 'Up':
            self.move_editor_cursor(0, -1)
        elif event.keysym == 'Down':
            self.move_editor_cursor(0, 1)
        elif event.keysym == 'Left':
            self.move_editor_cursor(-1, 0)
        elif event.keysym == 'Right':
            self.move_editor_cursor(1, 0)
        elif event.keysym == 'Escape':
            self.cancel_and_close()

    def save_and_close(self, event=None):
        """Converte a grade 8x8 em 8 bytes e fecha a janela, chamando o callback."""
        new_pattern = bytearray(8)
        for r in range(8):
            byte_val = 0
            for c in range(8):
                if self.pixel_data[r][c] == 1:
                    byte_val |= (1 << (7 - c))
            new_pattern[r] = byte_val

        self.callback(self.char_code, new_pattern)
        self.grab_release()
        self.destroy()

    def cancel_and_close(self, event=None):
        """Fecha a janela sem salvar, passando None no callback."""
        self.callback(self.char_code, None)
        self.grab_release()
        self.destroy()


# --- Aplicação Principal (CustomTkinter) ---

class FontEditorApp(CTk):
    """Gerencia a janela principal e a visualização 16x16 (32x32) da fonte."""

    def __init__(self, default_font_path):
        super().__init__()

        self.title("MSX Graphos III Font Editor (Python/CustomTkinter)")
        set_appearance_mode("Dark")
        set_default_color_theme("blue")

        self.font = MSXFont(default_font_path)
        self.selected_char_code = 32

        # Tamanhos
        # Escala 4x: Caractere 8x8 -> 32x32 pixels na tela
        self.char_display_scale = 4
        self.main_char_size = 8 * self.char_display_scale  # Tamanho do caractere: 32 pixels
        self.canvas_size = 16 * self.main_char_size + self.main_char_size  # 16 caracteres * 32px + margem (17 * 32px)

        # Cores
        self.COLOR_BG = '#1e1e1e'
        self.COLOR_FG = 'white'
        self.COLOR_PIXEL_ON = 'white'
        self.COLOR_PIXEL_OFF = '#303030'
        self.COLOR_CURSOR = '#1F6AA5'
        self.COLOR_MODIFIED = '#581845'

        # --- Layout Principal (Grid) ---
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # 1. Área de Visualização do Alfabeto (Frame esquerdo)
        font_frame = CTkFrame(self, fg_color="transparent")
        font_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nswe")

        self.font_canvas = Canvas(font_frame, width=self.canvas_size, height=self.canvas_size,
                                  bg=self.COLOR_BG, highlightthickness=2, highlightbackground=self.COLOR_CURSOR)
        self.font_canvas.pack(padx=5, pady=5)

        # 2. Área de Informações (Frame direito)
        info_frame = CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=1, padx=10, pady=10, sticky="n")

        self.info_label = CTkLabel(info_frame, text="", text_color=self.COLOR_FG, font=("Consolas", 14), justify=LEFT)
        self.info_label.pack(pady=(10, 20), anchor=W)

        CTkLabel(info_frame, text="Controles:", text_color=self.COLOR_FG, font=("Arial", 12, "bold")).pack(pady=(20, 0),
                                                                                                           anchor=W)
        controls = [
            ("Setas", "Navegar no Alfabeto"),
            ("ENTER / LMB", "Abrir Editor de Pixel"),
            ("Botão Direito / ENTER (Editor)", "Salvar Edição"),
            ("SPACE (Editor)", "Inverter Pixel"),
            ("Ctrl+S", "Salvar Fonte")
        ]
        for key, action in controls:
            CTkLabel(info_frame, text=f"• {key}: {action}", text_color=self.COLOR_FG, font=("Arial", 12),
                     justify=LEFT).pack(anchor=W)

        # 3. Botões de Ação (Abaixo do painel de info)
        button_frame = CTkFrame(info_frame, fg_color="transparent")
        button_frame.pack(pady=20, anchor=W)

        CTkButton(button_frame, text="Abrir Nova Fonte", command=self.load_font_dialog).pack(pady=5, fill='x')
        CTkButton(button_frame, text="Salvar Fonte", command=lambda: self.font.save()).pack(pady=5, fill='x')
        CTkButton(button_frame, text="Salvar Como...", command=self.save_font_as_dialog).pack(pady=5, fill='x')

        # Botão Encerrar
        CTkButton(button_frame, text="Encerrar", command=self.destroy, fg_color="#C0392B", hover_color="#E74C3C").pack(
            pady=(20, 5), fill='x')

        # --- Bindings e Inicialização ---
        self.font_canvas.bind('<Button-1>', self.on_char_click)
        self.bind('<Key>', self.on_key_press)
        self.bind('<Control-s>', lambda event: self.font.save())

        self.draw_grid()
        self.draw_font()
        self.update_info_label()

    def load_font_dialog(self):
        """Abre uma caixa de diálogo para carregar uma nova fonte."""
        filepath = filedialog.askopenfilename(
            title="Abrir Arquivo de Fonte (.ALF)",
            filetypes=[("Arquivos de Alfabeto MSX", "*.ALF"), ("Todos os arquivos", "*.*")]
        )
        if filepath:
            try:
                self.font = MSXFont(filepath)
                set_config(DEFAULT_FONT_PATH_KEY, filepath)
                self.draw_font()
                self.update_info_label()
            except Exception as e:
                messagebox.showerror("Erro ao Carregar", f"Não foi possível carregar a fonte: {e}")

    def save_font_as_dialog(self):
        """Abre uma caixa de diálogo para salvar a fonte com um novo nome."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".ALF",
            filetypes=[("Arquivos de Alfabeto MSX", "*.ALF"), ("Todos os arquivos", "*.*")],
            title="Salvar Fonte Como"
        )
        if filepath:
            self.font.save(filepath)

    def draw_grid(self):
        """Desenha a grade 16x16 e as coordenadas hexadecimais (0-F)."""
        start_offset = self.main_char_size

        for i in range(17):
            coord = i * self.main_char_size

            # Linhas horizontais (Grid)
            self.font_canvas.create_line(start_offset, coord + start_offset, self.canvas_size, coord + start_offset,
                                         fill=self.COLOR_PIXEL_OFF, tags="grid")
            # Linhas verticais (Grid)
            self.font_canvas.create_line(coord + start_offset, start_offset, coord + start_offset, self.canvas_size,
                                         fill=self.COLOR_PIXEL_OFF, tags="grid")

            # Coordenadas Hexa
            if i < 16:
                # Colunas (x)
                text_x = start_offset + (i * self.main_char_size) + (self.main_char_size / 2)
                self.font_canvas.create_text(text_x, start_offset / 2, text=f'{i:X}', fill=self.COLOR_CURSOR,
                                             font=("Consolas", 10), tags="coords")
                # Linhas (y)
                text_y = start_offset + (i * self.main_char_size) + (self.main_char_size / 2)
                self.font_canvas.create_text(start_offset / 2, text_y, text=f'{i:X}', fill=self.COLOR_CURSOR,
                                             font=("Consolas", 10), tags="coords")

    def draw_font(self):
        """Desenha todos os 256 caracteres no Canvas principal."""
        self.font_canvas.delete("char_pixels")

        start_offset = self.main_char_size

        for i in range(self.font.NUM_CHARS):
            row = i // 16
            col = i % 16

            x_start = start_offset + col * self.main_char_size
            y_start = start_offset + row * self.main_char_size

            # Desenha o fundo de "modificado"
            if i in self.font.modified_chars:
                self.font_canvas.create_rectangle(x_start, y_start, x_start + self.main_char_size,
                                                  y_start + self.main_char_size,
                                                  fill=self.COLOR_MODIFIED, outline="", tags="char_pixels")

            # Desenha os pixels do caractere
            pattern = self.font.get_char_pattern(i)
            if pattern:
                for y in range(8):
                    byte_data = pattern[y]
                    for x in range(8):
                        if (byte_data >> (7 - x)) & 1:
                            # Desenha o pixel ampliado (agora 4x4)
                            px = x_start + x * self.char_display_scale
                            py = y_start + y * self.char_display_scale
                            self.font_canvas.create_rectangle(
                                px, py,
                                px + self.char_display_scale, py + self.char_display_scale,
                                fill=self.COLOR_PIXEL_ON, outline="", tags="char_pixels"
                            )

        self.draw_cursor()

    def draw_cursor(self):
        """Desenha o retângulo de seleção (cursor) no caractere atual."""
        self.font_canvas.delete("cursor")

        row = self.selected_char_code // 16
        col = self.selected_char_code % 16

        start_offset = self.main_char_size
        x_start = start_offset + col * self.main_char_size
        y_start = start_offset + row * self.main_char_size

        self.font_canvas.create_rectangle(
            x_start, y_start,
            x_start + self.main_char_size, y_start + self.main_char_size,
            outline=self.COLOR_CURSOR, width=3, tags="cursor"
        )

    def update_info_label(self):
        """Atualiza o label com as informações do caractere selecionado."""
        code = self.selected_char_code
        row = code // 16
        col = code % 16

        char_repr = chr(code) if 32 <= code <= 126 else f'<{code}>'

        self.info_label.configure(text=
                                  f"Arquivo: {os.path.basename(self.font.filepath)}\n"
                                  f"Caractere (Dec): {code}\n"
                                  f"Caractere (Hex): 0x{code:02X}\n"
                                  f"Representação: '{char_repr}'\n\n"
                                  f"Coordenadas (Hex):\n"
                                  f"Linha: {row:X} (0x{row:02X})\n"
                                  f"Coluna: {col:X} (0x{col:02X})"
                                  )

    def move_cursor(self, dx, dy):
        """Move o cursor de seleção com wrap-around 16x16."""
        current_row = self.selected_char_code // 16
        current_col = self.selected_char_code % 16

        new_row = (current_row + dy) % 16
        new_col = (current_col + dx) % 16

        self.selected_char_code = new_row * 16 + new_col
        self.draw_cursor()
        self.update_info_label()

    def on_key_press(self, event):
        """Trata eventos de teclado para navegação e edição."""
        # Se o Canvas estiver focado (ou o mouse sobre ele)
        if self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery()) is self.font_canvas:
            if event.keysym == 'Up':
                self.move_cursor(0, -1)
            elif event.keysym == 'Down':
                self.move_cursor(0, 1)
            elif event.keysym == 'Left':
                self.move_cursor(-1, 0)
            elif event.keysym == 'Right':
                self.move_cursor(1, 0)
            elif event.keysym == 'Return':
                self.open_editor_window()

    def on_char_click(self, event):
        """Trata o clique do mouse no Canvas principal."""
        start_offset = self.main_char_size

        if event.x < start_offset or event.y < start_offset:
            return

        col = (event.x - start_offset) // self.main_char_size
        row = (event.y - start_offset) // self.main_char_size

        if 0 <= row < 16 and 0 <= col < 16:
            new_code = row * 16 + col

            if new_code == self.selected_char_code:
                self.open_editor_window()
            else:
                self.selected_char_code = new_code
                self.draw_cursor()
                self.update_info_label()

    def open_editor_window(self):
        """Abre a janela de edição 8x8 para o caractere selecionado."""
        char_code = self.selected_char_code
        current_pattern = list(self.font.get_char_pattern(char_code))

        EditorWindow(self, char_code, current_pattern, self.on_editor_close)

    def on_editor_close(self, char_code, new_pattern):
        """Callback chamado quando a janela de edição é fechada."""
        if new_pattern is not None:
            old_pattern = list(self.font.get_char_pattern(char_code))
            if old_pattern != new_pattern:
                self.font.update_char_pattern(char_code, new_pattern)
                self.draw_font()


# --- Execução Principal ---

if __name__ == '__main__':
    # 1. Configuração e obtenção do caminho da fonte padrão
    default_font_path = setup_config()

    # 2. Inicialização da Aplicação CustomTkinter principal
    app = FontEditorApp(default_font_path)
    app.mainloop()