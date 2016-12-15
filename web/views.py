# -*- coding: utf-8 -*-

import requests
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.shortcuts import redirect
from .models import Task, Passwordresetcodes
from django import forms
from datetime import datetime
import random
import string
import time

import os
from postmark import PMMail

random_str = lambda N: ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(N))


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def grecaptcha_verify(request):
    data = request.POST
    captcha_rs = data.get('g-recaptcha-response')
    url = "https://www.google.com/recaptcha/api/siteverify"
    params = {
        'secret': settings.RECAPTCHA_SECRET_KEY,
        'response': captcha_rs,
        'remoteip': get_client_ip(request)
    }
    verify_rs = requests.get(url, params=params, verify=True)
    verify_rs = verify_rs.json()
    return verify_rs.get("success", False)



def RateLimited(maxPerSecond): # a decorator. @RateLimited(10) will let 10 runs in 1 seconds
    minInterval = 1.0 / float(maxPerSecond)
    def decorate(func):
        lastTimeCalled = [0.0]
        def rateLimitedFunction(*args,**kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait>0:
                time.sleep(leftToWait)
            ret = func(*args,**kargs)
            lastTimeCalled[0] = time.clock()
            return ret
        return rateLimitedFunction
    return decorate


# Create your views here.
def index(request):
    if request.user.is_anonymous():
        return render(request, 'login.html')

    responsetxt = ''
    #thisuser = User.objects.get(username=request.user.username)

    tasks = Task.objects.filter(status = 'W', user=request.user, mothertask=None)
    waitingtasks = []

    for task in tasks:
        subtasks = Task.objects.filter(status='W', user=request.user, mothertask=task)
        waitingtasks.append({'text': task.text, 'id': task.id, 'subtasks': subtasks})
        #task['subtasks'] = subtask

    tasksDone = Task.objects.filter(status = 'D', user=request.user)
    context = {'tasks': waitingtasks, 'tasksDone': tasksDone}

    #return redirect('/login/?next=%s' % request.path)
    return render(request, 'index.html', context)


def register(request):
    if request.POST.has_key('requestcode'): #form is filled. if not spam, generate code and save in db, wait for email confirmation, return message
        #is this spam? check reCaptcha
        if not grecaptcha_verify(request): # captcha was not correct
            context = {'message': 'کپچای گوگل درست وارد نشده بود. شاید ربات هستید؟ کد یا کلیک یا تشخیص عکس زیر فرم را درست پر کنید. ببخشید که فرم به شکل اولیه برنگشته!'} #TODO: forgot password
            return render(request, 'register.html', context)

        if not User.objects.filter(username = request.POST['username']).exists(): #if user does not exists
                code = random_str(28)
                now = datetime.now()
                email = request.POST['email']
                password = request.POST['password']
                username = request.POST['username']
                temporarycode = Passwordresetcodes (email = email, time = now, code = code, username=username, password=password)
                temporarycode.save()
                message = PMMail(api_key = os.environ.get('POSTMARK_API_TOKEN'),
                                 subject = "فعال سازی اکانت تودو",
                                 sender = "jadi@jadi.net",
                                 to = email,
                                 text_body = "click on http://todoer.ir/accounts/register/?email={}&code={}".format(email, code),
                                 tag = "Create account")
                message.send()
                context = {'message': 'ایمیلی حاوی لینک فعال سازی اکانت به شما فرستاده شده، لطفا پس از چک کردن ایمیل، روی لینک کلیک کنید.'}
                return render(request, 'login.html', context)
        else:
            context = {'message': 'متاسفانه این نام کاربری قبلا استفاده شده است. از نام کاربری دیگری استفاده کنید. ببخشید که فرم ذخیره نشده. درست می شه'} #TODO: forgot password
            #TODO: keep the form data
            return render(request, 'register.html', context)
    elif request.GET.has_key('code'): # user clicked on code
        email = request.GET['email']
        code = request.GET['code']
        if Passwordresetcodes.objects.filter(code=code).exists(): #if code is in temporary db, read the data and create the user
            new_temp_user = Passwordresetcodes.objects.get(code=code)
            print new_temp_user
            print new_temp_user.password
            newuser = User.objects.create_user(username=new_temp_user.username, password=new_temp_user.password, email=email)
            Passwordresetcodes.objects.filter(code=code).delete() #delete the temporary activation code from db
            context = {'message': 'اکانت شما فعال شد. لاگین کنید - البته اگر دوست داشتی'}
            return render(request, 'login.html', context)
        else:
            context = {'message': 'این کد فعال سازی معتبر نیست. در صورت نیاز دوباره تلاش کنید'}
            return render(request, 'login.html', context)
    else:
        context = {'message': ''}
        return render(request, 'register.html', context)

@login_required
def taskdone(request, taskid):
    #thiscustomer = Customer.objects.filter(user=User.objects.filter(username=request.POST.get('customername')))[0]
    thisuser = request.user
    thisTask = Task.objects.get(id=taskid, user = thisuser)
    print (thisTask)
    thisTask.status = 'D'
    thisTask.save()
    return redirect('/')

@login_required
def taskadd(request):
    tasktext = request.POST['tasktext']
    savedate = datetime.now()
    try:
        mothertask = Task.objects.get(id=request.POST['mothertask'], user=request.user)
    except:
        mothertask =  None

    thisTask = Task(text=tasktext, status='W', createdate = savedate, user=request.user, mothertask=mothertask)
    thisTask.save()
    return redirect('/')

@login_required
def taskredo(request, taskid):
    #thiscustomer = Customer.objects.filter(user=User.objects.filter(username=request.POST.get('customername')))[0]
    thisuser = request.user
    thisTask = Task.objects.get(id=taskid, user = thisuser)
    print (thisTask)
    thisTask.status = 'W'
    thisTask.save()
    return redirect('/')


def logout_page(request):
    if not request.user.is_anonymous():
        logout(request)
    return redirect('/')

@RateLimited(4)
def login_page(request):
    if ('dologin' in request.POST):
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('/')
            else:
                return HttpResponse('your account is disabled')
        else:
                context = {'message': 'نام کاربری یا کلمه عبور اشتباه بود'}
                return render(request, 'login.html', context)
    else:
        return render(request, 'login.html')
