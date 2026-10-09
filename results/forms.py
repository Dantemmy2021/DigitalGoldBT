from django import forms
from .models import StudentNote, StudentClass, Subject, TERM_CHOICES, AdmissionApplication
from ckeditor_uploader.widgets import CKEditorUploadingWidget

SESSION_CHOICES = [
    ('2023/2024', '2023/2024'),
    ('2024/2025', '2024/2025'),
    ('2025/2026', '2025/2026'),
    ('2026/2027', '2026/2027'),
]

class StudentNoteForm(forms.ModelForm):
    term = forms.ChoiceField(choices=TERM_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    session = forms.ChoiceField(choices=SESSION_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = StudentNote
        fields = ['student_class', 'subject', 'term', 'session', 'title', 'note', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'note': CKEditorUploadingWidget(),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school')
        super().__init__(*args, **kwargs)
        self.fields['student_class'].queryset = StudentClass.objects.filter(school=school)
        self.fields['student_class'].widget.attrs.update({'class': 'form-select'})
        self.fields['subject'].queryset = Subject.objects.filter(school=school).order_by('name')
        self.fields['subject'].widget.attrs.update({'class': 'form-select'})
        self.initial['session'] = school.current_session

class AdmissionForm(forms.ModelForm):
    class Meta:
        model = AdmissionApplication
        fields = [
            'full_name','date_of_birth','gender','class_applying','previous_school',
            'parent_name','parent_phone','parent_email','parent_address','relationship','passport'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type':'date', 'class':'form-control'}),
            'parent_address': forms.Textarea(attrs={'rows':3, 'class':'form-control'}),
            'full_name': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Student Full Name'}),
            'class_applying': forms.TextInput(attrs={'class':'form-control', 'placeholder':'e.g JSS1, SS2, Primary 1'}),
            'previous_school': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Previous School (optional)'}),
            'parent_name': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Parent Full Name'}),
            'parent_phone': forms.TextInput(attrs={'class':'form-control', 'placeholder':'080...'}),
            'parent_email': forms.EmailInput(attrs={'class':'form-control', 'placeholder':'email@example.com (optional)'}),
            'relationship': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Father / Mother / Guardian'}),
            'gender': forms.Select(attrs={'class':'form-select'}),
            'passport': forms.FileInput(attrs={'class':'form-control'}),
        }